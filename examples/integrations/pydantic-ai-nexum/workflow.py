"""
Nexum workflow definition for Pydantic AI tool calls.

Each tool call becomes a single-node workflow:
  START -> EFFECT("tool_call") -> END

The workflow input is:
  {"tool_name": "web_search", "tool_args": {"query": "..."}}
"""

from pydantic import BaseModel
from nexum import workflow


class ToolCallOutput(BaseModel):
    result: str


def _tool_call_handler(ctx):
    # Placeholder — actual execution lives in worker.py
    raise RuntimeError("tool_call handler should be executed by worker.py, not inline")


tool_call_workflow = (
    workflow("pydantic-tool-call")
    .effect("tool_call", ToolCallOutput, handler=_tool_call_handler, depends_on=[])
    .build()
)
