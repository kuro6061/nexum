"""
Nexum workflow definition for smolagents tool calls.

Each tool call becomes a single-node workflow:
  START -> EFFECT("tool_call") -> END

The workflow input is:
  {"tool_name": "web_search", "tool_args": {"query": "..."}}
"""

import sys
import os


from pydantic import BaseModel
from nexum import workflow


class ToolCallOutput(BaseModel):
    result: str


def _tool_call_handler(ctx):
    # This handler is only used by the worker; it's a placeholder in the
    # workflow definition so the SDK has something to register.  The real
    # execution logic lives in worker.py.
    raise RuntimeError("tool_call handler should be executed by worker.py, not inline")


tool_call_workflow = (
    workflow("smolagents-tool-call")
    .effect("tool_call", ToolCallOutput, handler=_tool_call_handler, depends_on=[])
    .build()
)
