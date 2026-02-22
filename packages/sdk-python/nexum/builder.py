from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Type

from pydantic import BaseModel

from .context import ContextView


class NodeDef:
    def __init__(
        self,
        node_id: str,
        node_type: str,  # COMPUTE, EFFECT, ROUTER, HUMAN_APPROVAL, TIMER
        output_model: Type[BaseModel] | None,
        handler: Callable | None,
        dependencies: list[str],
        delay_seconds: int | None = None,
    ):
        self.id = node_id
        self.type = node_type
        self.output_model = output_model
        self.handler = handler
        self.dependencies = dependencies
        self.delay_seconds = delay_seconds


class WorkflowDef:
    def __init__(self, workflow_id: str, version_hash: str, ir_json: str, nodes: list[NodeDef]):
        self.workflow_id = workflow_id
        self.version_hash = version_hash
        self.ir_json = ir_json
        self.nodes = nodes
        self._node_map = {n.id: n for n in nodes}

    def get_node(self, node_id: str) -> NodeDef | None:
        return self._node_map.get(node_id)


class WorkflowBuilder:
    """
    Fluent builder for defining a Nexum workflow.

    Example::

        from nexum.builder import workflow
        from pydantic import BaseModel

        class SearchResult(BaseModel):
            content: str

        class Summary(BaseModel):
            text: str

        wf = (
            workflow("my-workflow")
            .effect("search", SearchResult, fetch_data)
            .compute("summarize", Summary, summarize)
            .build()
        )
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self._nodes: list[NodeDef] = []
        self._node_order: list[str] = []

    def _current_deps(self) -> list[str]:
        """Default dependency = all previous nodes (matches TS SDK behavior)."""
        return list(self._node_order)

    def effect(
        self,
        node_id: str,
        output_model: Type[BaseModel],
        handler: Callable,
        *,
        depends_on: list[str] | None = None,
    ) -> WorkflowBuilder:
        """
        Add an **EFFECT** node — a side-effectful async operation (API call, DB write, etc.).

        Executed with **exactly-once** semantics and automatic retry.
        Depends on all preceding nodes by default; use ``depends_on`` for explicit fan-in.

        :param node_id: Unique node identifier within this workflow.
        :param output_model: Pydantic BaseModel class defining the output schema.
        :param handler: Async callable receiving a ``ContextView`` and returning ``output_model``.
        :param depends_on: Explicit list of node IDs to depend on (overrides sequential default).
        """
        deps = depends_on if depends_on is not None else self._current_deps()
        self._nodes.append(NodeDef(node_id, "EFFECT", output_model, handler, deps))
        self._node_order.append(node_id)
        return self

    def compute(
        self,
        node_id: str,
        output_model: Type[BaseModel],
        handler: Callable,
        *,
        depends_on: list[str] | None = None,
    ) -> WorkflowBuilder:
        """
        Add a **COMPUTE** node — a pure, deterministic function.

        Compute nodes are not retried on failure (use ``effect`` for fallible operations).
        Depends on all preceding nodes by default.

        :param node_id: Unique node identifier within this workflow.
        :param output_model: Pydantic BaseModel class defining the output schema.
        :param handler: Callable receiving a ``ContextView`` and returning ``output_model``.
        :param depends_on: Explicit list of node IDs to depend on.
        """
        deps = depends_on if depends_on is not None else self._current_deps()
        self._nodes.append(NodeDef(node_id, "COMPUTE", output_model, handler, deps))
        self._node_order.append(node_id)
        return self

    def timer(
        self,
        node_id: str,
        delay_seconds: int,
        *,
        depends_on: list[str] | None = None,
    ) -> WorkflowBuilder:
        """
        Add a **TIMER** node — waits for a specified duration before proceeding.

        The server handles the delay durably; no worker is needed.

        :param node_id: Unique node identifier.
        :param delay_seconds: Number of seconds to wait before scheduling the next node.
        :param depends_on: Explicit list of node IDs to depend on.
        """
        deps = depends_on if depends_on is not None else self._current_deps()
        self._nodes.append(NodeDef(node_id, "TIMER", None, None, deps, delay_seconds=delay_seconds))
        self._node_order.append(node_id)
        return self

    def build(self) -> WorkflowDef:
        """
        Compile the workflow definition into a :class:`WorkflowDef`.

        Computes a deterministic SHA-256 ``version_hash`` from the IR JSON,
        enabling safe version upgrades and exactly-once execution semantics.

        :returns: A :class:`WorkflowDef` ready to be registered with :class:`~nexum.client.NexumClient`.
        """
        # Build IR JSON matching the TypeScript SDK format
        ir_nodes: dict[str, Any] = {}
        for n in self._nodes:
            node_ir: dict[str, Any] = {
                "type": n.type,
                "dependencies": n.dependencies,
            }
            if n.delay_seconds is not None:
                node_ir["delay_seconds"] = n.delay_seconds
            ir_nodes[n.id] = node_ir
        ir_json = json.dumps({"nodes": ir_nodes})
        version_hash = "sha256:" + hashlib.sha256(ir_json.encode()).hexdigest()
        return WorkflowDef(self.workflow_id, version_hash, ir_json, list(self._nodes))


def workflow(workflow_id: str) -> WorkflowBuilder:
    """
    Entry point for the Nexum Python SDK. Returns a :class:`WorkflowBuilder`.

    :param workflow_id: Globally unique identifier for this workflow.

    Example::

        from nexum.builder import workflow
        wf = workflow("my-workflow").effect(...).compute(...).build()
    """
    return WorkflowBuilder(workflow_id)
