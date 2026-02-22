"""
demo.py — LangGraph + Nexum: exactly-once tool execution.

LangGraph already supports checkpointing (MemorySaver, SqliteSaver), which
saves graph state and resumes conversations. However, on resume, LangGraph
re-executes tool calls from the latest checkpoint — results are not cached.

Nexum complements LangGraph by making each tool call exactly-once:
- LangGraph checkpoint = "which node am I at?"
- Nexum tool cache   = "what did each tool return?"

Usage:
    # Terminal 1
    nexum dev

    # Terminal 2
    python worker.py

    # Terminal 3
    GEMINI_API_KEY=... python demo.py "What is the latest on LangGraph?"

    # Re-run same query — tool calls load from Nexum cache ⚡
    SESSION_ID=my-session GEMINI_API_KEY=... python demo.py "What is the latest on LangGraph?"
"""

import os
import sys

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from submit_task import submit_tool_call

SESSION_ID = os.environ.get("SESSION_ID", "default")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

if not GEMINI_KEY and not OPENAI_KEY:
    print("ERROR: Set GEMINI_API_KEY or OPENAI_API_KEY")
    sys.exit(1)


def _get_model():
    if GEMINI_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GEMINI_KEY)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_KEY)


@tool
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


@tool
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


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is durable execution for AI agents?"

    print(f"Query: {query}")
    print(f"Session: {SESSION_ID}")
    print("-" * 60)

    model = _get_model()
    agent = create_react_agent(model, tools=[web_search, visit_webpage])

    result = agent.invoke({"messages": [("human", query)]})
    final = result["messages"][-1].content
    print("\n" + "=" * 60)
    print(final)
