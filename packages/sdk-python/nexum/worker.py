from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
import logging
from typing import Any

from pydantic import BaseModel

from .context import ContextView
from .client import NexumClient

logger = logging.getLogger("nexum")


class Worker:
    def __init__(
        self,
        workflows: list,
        *,
        concurrency: int = 4,
        poll_interval: float = 0.5,
        host: str = "localhost",
        port: int = 50051,
    ):
        self._workflows = workflows
        self._workflow_map = {wf.workflow_id: wf for wf in workflows}
        self._version_hashes = {wf.version_hash: wf for wf in workflows}
        self._concurrency = concurrency
        self._poll_interval = poll_interval
        self._client = NexumClient(host=host, port=port)
        self._worker_id = f"py-worker-{uuid.uuid4().hex[:8]}"
        self._running = False
        self._semaphore: asyncio.Semaphore | None = None

    async def run_until_complete(self, execution_id: str, timeout: float = 60) -> dict:
        """Start worker and wait for specific execution to complete."""
        self._running = True
        worker_task = asyncio.create_task(self._run())

        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                status = self._client.get_status(execution_id)
                if status["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
                    self._running = False
                    worker_task.cancel()
                    if status["status"] == "FAILED":
                        raise RuntimeError(f"Execution {execution_id} failed")
                    return status["completedNodes"]
                await asyncio.sleep(0.5)
        finally:
            self._running = False
            worker_task.cancel()

        raise TimeoutError(f"Execution {execution_id} did not complete within {timeout}s")

    async def _run(self) -> None:
        self._semaphore = asyncio.Semaphore(self._concurrency)

        while self._running:
            try:
                # Poll for each registered workflow version
                for wf in self._workflows:
                    if not self._running:
                        return
                    resp = self._client.poll_task(self._worker_id, wf.version_hash)
                    if resp.has_task:
                        asyncio.ensure_future(self._handle_task(resp, wf))
                        break
                else:
                    await asyncio.sleep(self._poll_interval)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(1.0)

    async def _handle_task(self, task, wf) -> None:
        async with self._semaphore:
            try:
                await self._execute_task(task, wf)
            except Exception as e:
                logger.error(f"Task {task.task_id} failed: {e}")
                try:
                    self._client.fail_task(task.task_id, str(e))
                except Exception:
                    pass

    async def _execute_task(self, task, wf) -> None:
        node = wf.get_node(task.node_id)
        if node is None:
            raise RuntimeError(f"Unknown node: {task.node_id}")

        # Parse input_json — server sends { input: {...}, deps: {...} }
        input_data_raw = json.loads(task.input_json) if task.input_json else {}
        input_data = input_data_raw.get("input", input_data_raw)
        deps_raw = input_data_raw.get("deps", {})

        # Deserialize deps into Pydantic models where possible
        outputs: dict[str, Any] = {}
        for k, v in deps_raw.items():
            dep_node = wf.get_node(k)
            if dep_node and dep_node.output_model and isinstance(v, dict):
                try:
                    outputs[k] = dep_node.output_model.model_validate(v)
                except Exception:
                    outputs[k] = v
            else:
                outputs[k] = v

        ctx = ContextView(input_data=input_data, outputs=outputs)

        logger.info(f"[NEXUM] {node.type} {node.id} → executing")

        if node.handler is None:
            raise RuntimeError(f"Node {node.id} has no handler")

        if inspect.iscoroutinefunction(node.handler):
            result = await node.handler(ctx)
        else:
            result = node.handler(ctx)

        # Validate output with Pydantic
        if node.output_model and not isinstance(result, node.output_model):
            if isinstance(result, dict):
                result = node.output_model.model_validate(result)
            else:
                raise TypeError(f"Handler for {node.id} returned wrong type: {type(result)}")

        # Serialize output
        if isinstance(result, BaseModel):
            output_json = result.model_dump_json()
        else:
            output_json = json.dumps(result)

        self._client.complete_task(task.task_id, json.loads(output_json))
        logger.info(f"[NEXUM] {node.type} {node.id} → completed")


def worker(workflows: list, *, concurrency: int = 4, **kwargs) -> Worker:
    return Worker(workflows, concurrency=concurrency, **kwargs)
