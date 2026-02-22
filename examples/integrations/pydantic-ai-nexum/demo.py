"""
demo.py — Pydantic AI + Nexum: durable tool calls for AI agents.

Pydantic AI agent with web_search and visit_webpage tools backed by Nexum.
Every tool call is persisted in SQLite — if the process crashes and restarts
with the same SESSION_ID, already-completed tool calls return from cache
instantly instead of re-executing.

Usage:
    # Terminal 1: start Nexum server
    nexum dev

    # Terminal 2: start worker
    python worker.py

    # Terminal 3: run agent
    python demo.py "What are the main differences between Nexum and Temporal?"

    # Re-run the same query — tool calls load from Nexum cache
    SESSION_ID=my-session python demo.py "What are the main differences between Nexum and Temporal?"
"""

import os
import sys

from pydantic_ai import Agent

from submit_task import submit_tool_call

# ── Model selection ──────────────────────────────────────────────────────────
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
SESSION_ID = os.environ.get("SESSION_ID", "default")

if GEMINI_KEY:
    MODEL = "google-gla:gemini-2.0-flash"
elif OPENAI_KEY:
    MODEL = "openai:gpt-4o-mini"
else:
    print("ERROR: Set GEMINI_API_KEY or OPENAI_API_KEY")
    sys.exit(1)

# ── Agent definition ─────────────────────────────────────────────────────────
agent = Agent(
    MODEL,
    system_prompt=(
        "You are a research assistant. When you need information, use the "
        "web_search tool to find relevant results, and visit_webpage to read "
        "specific pages in detail. Synthesize what you find into a clear, "
        "well-structured answer."
    ),
)


@agent.tool_plain
def web_search(query: str) -> str:
    """Search the web for information about a topic.

    Args:
        query: The search query string.

    Returns:
        JSON list of search results with title, URL, and snippet.
    """
    return submit_tool_call(
        "web_search",
        {"query": query, "max_results": 5},
        session_id=SESSION_ID,
    )


@agent.tool_plain
def visit_webpage(url: str) -> str:
    """Fetch and read the content of a webpage.

    Args:
        url: The URL to fetch.

    Returns:
        Markdown-formatted text content of the page.
    """
    return submit_tool_call(
        "visit_webpage",
        {"url": url},
        session_id=SESSION_ID,
    )


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is durable execution for AI agents?"

    print(f"Query: {query}")
    print(f"Session: {SESSION_ID}")
    print(f"Model: {MODEL}")
    print("-" * 60)

    result = agent.run_sync(query)
    print("\n" + "=" * 60)
    print(result.output)
