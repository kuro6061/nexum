from __future__ import annotations

import json
from typing import Any

import grpc

from .proto import nexum_pb2, nexum_pb2_grpc


class NexumClient:
    def __init__(self, host: str = "localhost", port: int = 50051):
        self._channel = grpc.insecure_channel(f"{host}:{port}")
        self._stub = nexum_pb2_grpc.NexumServiceStub(self._channel)

    def register_workflow(self, wf) -> str:
        """Register a workflow and return compatibility status."""
        req = nexum_pb2.WorkflowIR(
            workflow_id=wf.workflow_id,
            version_hash=wf.version_hash,
            ir_json=wf.ir_json,
        )
        resp = self._stub.RegisterWorkflow(req)
        if not resp.ok:
            raise RuntimeError(f"RegisterWorkflow failed: {resp.message}")
        return resp.compatibility

    def start_execution(self, workflow_id: str, input_data: dict, version_hash: str = "") -> str:
        req = nexum_pb2.StartRequest(
            workflow_id=workflow_id,
            version_hash=version_hash,
            input_json=json.dumps(input_data),
        )
        resp = self._stub.StartExecution(req)
        return resp.execution_id

    def get_status(self, execution_id: str) -> dict:
        req = nexum_pb2.StatusRequest(execution_id=execution_id)
        resp = self._stub.GetStatus(req)
        completed_nodes: dict[str, Any] = {}
        if resp.completed_nodes_json:
            try:
                completed_nodes = json.loads(resp.completed_nodes_json)
            except json.JSONDecodeError:
                pass
        return {
            "status": resp.status,
            "completedNodes": completed_nodes,
        }

    def poll_task(self, worker_id: str, version_hash: str):
        req = nexum_pb2.PollRequest(
            worker_id=worker_id,
            version_hash=version_hash,
        )
        return self._stub.PollTask(req)

    def complete_task(self, task_id: str, output: Any) -> None:
        output_json = json.dumps(output) if not isinstance(output, str) else output
        req = nexum_pb2.CompleteRequest(
            task_id=task_id,
            output_json=output_json,
        )
        self._stub.CompleteTask(req)

    def fail_task(self, task_id: str, error: str) -> None:
        req = nexum_pb2.FailRequest(
            task_id=task_id,
            error_message=error,
        )
        self._stub.FailTask(req)

    def close(self) -> None:
        self._channel.close()
