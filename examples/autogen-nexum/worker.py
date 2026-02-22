"""
worker.py — Nexum worker that handles 'tool_call' EFFECT nodes for AutoGen.

Executes web_search (DuckDuckGo) and visit_webpage (markdownify) tools
when tasks arrive from the Nexum server.

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class ToolCallOutput(BaseModel):
    result: str


def handle_tool_call(ctx):
    """Execute a tool and return its result."""
    tool_name = ctx.input["tool_name"]
    tool_args = dict(ctx.input["tool_args"])

    logger.info(f"Executing tool '{tool_name}' with args: {json.dumps(tool_args)[:200]}")

    if tool_name == "web_search":
        from ddgs import DDGS
        query = tool_args.get("query", "")
        max_results = tool_args.get("max_results", 10)
        ddg = DDGS()
        try:
            results = list(ddg.text(query, max_results=max_results))
            result_str = json.dumps(results)
            logger.info(f"web_search returned {len(results)} results ({len(result_str)} chars)")
            return ToolCallOutput(result=result_str)
        except Exception as e:
            logger.warning(f"DDGS error: {e}")
            raise

    if tool_name == "visit_webpage":
        import urllib.request
        url = tool_args.get("url", "")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            # Try markdownify if available
            try:
                from markdownify import markdownify
                result_str = markdownify(content)[:8000]
            except ImportError:
                # Fallback: strip HTML tags crudely
                import re
                result_str = re.sub(r"<[^>]+>", "", content)[:8000]
            logger.info(f"visit_webpage returned {len(result_str)} chars from {url}")
            return ToolCallOutput(result=result_str)
        except Exception as e:
            logger.warning(f"visit_webpage error: {e}")
            raise

    raise ValueError(f"Unknown tool: {tool_name}. Available: web_search, visit_webpage")


# Workflow definition (must match submit_task.py)
tool_call_workflow = (
    workflow("autogen-tool-call")
    .effect("tool_call", ToolCallOutput, handler=handle_tool_call, depends_on=[])
    .build()
)


async def main():
    client = NexumClient()

    compat = client.register_workflow(tool_call_workflow)
    logger.info(f"Registered workflow: {tool_call_workflow.workflow_id} (compatibility: {compat})")

    logger.info("Worker started. Waiting for tasks on localhost:50051 ...")
    w = Worker([tool_call_workflow], concurrency=4, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
