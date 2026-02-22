"""
worker.py — Nexum worker for OpenAI Agents SDK tool calls.

Executes web_search (DuckDuckGo) and visit_webpage tools.

Usage:
    python worker.py
"""

import asyncio
import json
import logging

from pydantic import BaseModel
from nexum import workflow, NexumClient, Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class ToolCallOutput(BaseModel):
    result: str


def handle_tool_call(ctx):
    tool_name = ctx.input["tool_name"]
    tool_args = dict(ctx.input["tool_args"])

    logger.info(f"Executing tool '{tool_name}'")

    if tool_name == "web_search":
        from ddgs import DDGS
        query = tool_args.get("query", "")
        max_results = tool_args.get("max_results", 10)
        results = list(DDGS().text(query, max_results=max_results))
        return ToolCallOutput(result=json.dumps(results))

    if tool_name == "visit_webpage":
        import urllib.request
        url = tool_args.get("url", "")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        try:
            from markdownify import markdownify
            text = markdownify(content)[:8000]
        except ImportError:
            import re
            text = re.sub(r"<[^>]+>", "", content)[:8000]
        return ToolCallOutput(result=text)

    raise ValueError(f"Unknown tool: {tool_name}")


tool_call_workflow = (
    workflow("openai-agents-tool-call")
    .effect("tool_call", ToolCallOutput, handler=handle_tool_call, depends_on=[])
    .build()
)


async def main():
    client = NexumClient()
    compat = client.register_workflow(tool_call_workflow)
    logger.info(f"Registered workflow (compatibility: {compat})")
    logger.info("Worker started on localhost:50051 ...")
    w = Worker([tool_call_workflow], concurrency=4, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
