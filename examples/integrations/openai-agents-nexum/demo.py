"""
demo.py — OpenAI Agents SDK + Nexum: durable tool calls.

Usage:
    # Terminal 1
    nexum dev

    # Terminal 2
    python worker.py

    # Terminal 3
    OPENAI_API_KEY=... python demo.py "What is durable execution?"

    # Re-run — tool calls load from Nexum cache ⚡
    SESSION_ID=my-session OPENAI_API_KEY=... python demo.py "What is durable execution?"
"""

import asyncio
import os
import sys

from agents import Agent, Runner, function_tool

from submit_task import submit_tool_call

SESSION_ID = os.environ.get("SESSION_ID", "default")

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not OPENAI_KEY and not GEMINI_KEY:
    print("ERROR: Set OPENAI_API_KEY or GEMINI_API_KEY")
    sys.exit(1)

# OpenAI Agents SDK uses OpenAI model names or litellm-compatible strings
MODEL = "gpt-4o-mini" if OPENAI_KEY else "gemini/gemini-2.0-flash"


@function_tool
def web_search(query: str) -> str:
    """Search the web for information about a topic.

    Args:
        query: The search query string.
    """
    return submit_tool_call(
        "web_search",
        {"query": query, "max_results": 5},
        session_id=SESSION_ID,
    )


@function_tool
def visit_webpage(url: str) -> str:
    """Fetch and read the content of a webpage.

    Args:
        url: The URL to fetch.
    """
    return submit_tool_call(
        "visit_webpage",
        {"url": url},
        session_id=SESSION_ID,
    )


agent = Agent(
    name="ResearchAgent",
    model=MODEL,
    instructions=(
        "You are a research assistant. Use web_search to find information "
        "and visit_webpage to read specific pages. Synthesize your findings "
        "into a clear, well-structured answer."
    ),
    tools=[web_search, visit_webpage],
)


async def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is durable execution for AI agents?"

    print(f"Query: {query}")
    print(f"Session: {SESSION_ID}")
    print(f"Model: {MODEL}")
    print("-" * 60)

    result = await Runner.run(agent, query)
    print("\n" + "=" * 60)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
