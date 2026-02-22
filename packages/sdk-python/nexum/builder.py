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
        deps = depends_on if depends_on is not None else self._current_deps()
        self._nodes.append(NodeDef(node_id, "TIMER", None, None, deps, delay_seconds=delay_seconds))
        self._node_order.append(node_id)
        return self

    def build(self) -> WorkflowDef:
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
    return WorkflowBuilder(workflow_id)
