"""
worker.py - Nexum worker for deep-research-nexum.

Handles 'search_and_learn' EFFECT nodes:
  1. DuckDuckGo search (free, no API key)
  2. Gemini LLM extracts key learnings from results

Usage:
    PYTHONIOENCODING=utf-8 python worker.py
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'packages', 'sdk-python'))

from pydantic import BaseModel
from nexum import workflow, NexumClient, Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class LearnResult(BaseModel):
    query: str
    research_goal: str
    learnings: list[str]   # 3-5 key learnings
    urls: list[str]        # source URLs


def handle_search_and_learn(ctx) -> LearnResult:
    """
    Search DuckDuckGo for a query and extract key learnings via Gemini.

    Input:
        query (str): The SERP query string
        research_goal (str): What we want to learn from this query

    Output:
        LearnResult with learnings and source URLs
    """
    from ddgs import DDGS
    from openai import OpenAI

    query = ctx.input["query"]
    research_goal = ctx.input["research_goal"]
    logger.info(f"Searching: {query}")

    # --- Step 1: DuckDuckGo search (free, no API key) ---
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))

    if not results:
        logger.warning(f"No results for query: {query}")
        return LearnResult(query=query, research_goal=research_goal, learnings=[], urls=[])

    urls = [r['href'] for r in results]
    contents = "\n\n".join([
        f"[{i+1}] {r['title']}\nURL: {r['href']}\n{r['body']}"
        for i, r in enumerate(results)
    ])
    logger.info(f"Found {len(results)} results for: {query}")

    # --- Step 2: Gemini LLM - extract learnings ---
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    client = OpenAI(
        api_key=gemini_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Extract key learnings from web search results. "
                    "Be concise, specific, and information-dense. Include numbers, dates, and key entities."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Research goal: {research_goal}\n"
                    f"Query: {query}\n\n"
                    f"Search results:\n{contents}\n\n"
                    "Extract 3-5 key learnings. Each learning must be a single, self-contained sentence "
                    "that is densely informative. Start each learning with '- '."
                ),
            },
        ],
        max_tokens=1024,
    )

    raw = response.choices[0].message.content.strip()
    learnings = [
        line.lstrip("- •").strip()
        for line in raw.split("\n")
        if line.strip().startswith(("-", "•")) and len(line.strip()) > 10
    ]
    if not learnings:
        learnings = [raw]  # fallback: use raw response as one learning

    logger.info(f"Extracted {len(learnings)} learnings for: {query}")
    return LearnResult(
        query=query,
        research_goal=research_goal,
        learnings=learnings,
        urls=urls,
    )


# --- Workflow definition ---
research_workflow = (
    workflow("deep-research")
    .effect("search_and_learn", LearnResult, handler=handle_search_and_learn, depends_on=[])
    .build()
)


async def main():
    client = NexumClient()
    compat = client.register_workflow(research_workflow)
    logger.info(f"Registered workflow: {research_workflow.workflow_id} (compatibility: {compat})")
    logger.info("Worker started. Waiting for tasks on localhost:50051 ...")
    w = Worker([research_workflow], concurrency=4, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
