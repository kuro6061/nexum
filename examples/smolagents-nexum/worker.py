"""
worker.py — Nexum worker that handles 'tool_call' EFFECT nodes.

Instantiates the smolagents tools and executes them when a task arrives.
The worker connects to localhost:50051 (Nexum server must already be running).

Usage:
    python worker.py
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from pydantic import BaseModel
from nexum import workflow, NexumClient, Worker

from smolagents import DuckDuckGoSearchTool, VisitWebpageTool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── smolagents tools ────────────────────────────────────────────────
TOOLS = {
    "web_search": DuckDuckGoSearchTool(),
    "visit_webpage": VisitWebpageTool(),
}


class ToolCallOutput(BaseModel):
    result: str


def handle_tool_call(ctx):
    """Execute a smolagents tool and return its result."""
    tool_name = ctx.input["tool_name"]
    tool_args = dict(ctx.input["tool_args"])  # mutable copy

    logger.info(f"Executing tool '{tool_name}' with args: {json.dumps(tool_args)[:200]}")

    # web_search: use DDGS directly so we can support max_results kwarg
    # (smolagents DuckDuckGoSearchTool.forward() doesn't accept max_results)
    if tool_name == "web_search":
        from ddgs import DDGS
        query = tool_args.get("query", "")
        max_results = tool_args.get("max_results", 10)
        ddg = DDGS()
        try:
            results = list(ddg.text(query, max_results=max_results))
        except Exception as e:
            logger.warning(f"DDGS error: {e}, retrying with DuckDuckGoSearchTool")
            results_str = TOOLS["web_search"](query)
            logger.info(f"Tool 'web_search' returned {len(results_str)} chars")
            return ToolCallOutput(result=results_str)
        result_str = json.dumps(results)
        logger.info(f"Tool 'web_search' returned {len(results)} results ({len(result_str)} chars)")
        return ToolCallOutput(result=result_str)

    tool = TOOLS.get(tool_name)
    if tool is None:
        raise ValueError(f"Unknown tool: {tool_name}. Available: {list(TOOLS.keys())}")

    # smolagents tools are callable: tool(**kwargs) -> str
    result = tool(**tool_args)
    result_str = str(result)

    logger.info(f"Tool '{tool_name}' returned {len(result_str)} chars")
    return ToolCallOutput(result=result_str)


# ── Workflow definition (must match what submit_task registers) ─────
tool_call_workflow = (
    workflow("smolagents-tool-call")
    .effect("tool_call", ToolCallOutput, handler=handle_tool_call, depends_on=[])
    .build()
)


async def main():
    client = NexumClient()

    # Register workflow
    compat = client.register_workflow(tool_call_workflow)
    logger.info(f"Registered workflow: {tool_call_workflow.workflow_id} (compatibility: {compat})")

    # Start worker — runs forever, polling for tasks
    logger.info("Worker started. Waiting for tasks on localhost:50051 ...")
    w = Worker([tool_call_workflow], concurrency=4, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
