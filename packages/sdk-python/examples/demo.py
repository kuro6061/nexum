"""
Nexum Python SDK Demo
Equivalent of examples/demo/run.ts
"""
import asyncio
import sys
import os
import logging

# Add parent directory to path so we can import the nexum package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import BaseModel
from nexum import workflow, NexumClient, worker

logging.basicConfig(level=logging.INFO)


# Schemas
class SearchResult(BaseModel):
    content: str
    score: float


class Summary(BaseModel):
    text: str
    word_count: int


# Handlers
async def do_search(ctx):
    query = ctx.input.get("query", "default")
    await asyncio.sleep(0.1)
    return SearchResult(
        content=f"Found relevant information about: {query}",
        score=0.92,
    )


def do_summarize(ctx):
    result = ctx.get("search")
    text = f"Summary: {result.content} (score: {result.score})"
    return Summary(text=text, word_count=len(text.split()))


# Workflow
research_agent = (
    workflow("ResearchAgentPy")
    .effect("search", SearchResult, handler=do_search)
    .compute("summarize", Summary, handler=do_summarize)
    .build()
)


async def main():
    client = NexumClient()

    # Register workflow
    compat = client.register_workflow(research_agent)
    print(f"Registered workflow: {research_agent.workflow_id} (compatibility: {compat})")

    # Start execution
    exec_id = client.start_execution(
        research_agent.workflow_id,
        {"query": "Durable Execution for LLM Agents"},
        version_hash=research_agent.version_hash,
    )
    print(f"Started execution: {exec_id}")

    # Run worker until execution completes
    w = worker([research_agent], concurrency=2)
    result = await w.run_until_complete(exec_id, timeout=30)

    print(f"\nResult:")
    print(f"  Search: {result.get('search', {})}")
    print(f"  Summary: {result.get('summarize', {})}")
    print("\n[SUCCESS] Python SDK demo completed!")


asyncio.run(main())
