"""
benchmark.py — Plain LangGraph vs LangGraph + Nexum timing.

Usage:
    GEMINI_API_KEY=... python benchmark.py
"""

import os
import sys
import time
import json

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

QUERY = "What are the key features of LangGraph compared to LangChain?"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DIVIDER = "=" * 60

if not GEMINI_KEY and not OPENAI_KEY:
    print("ERROR: Set GEMINI_API_KEY or OPENAI_API_KEY")
    sys.exit(1)


def _get_model():
    if GEMINI_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GEMINI_KEY)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_KEY)


def make_plain_agent():
    from ddgs import DDGS

    @tool
    def web_search(query: str) -> str:
        """Search the web. Args: query: Search query."""
        return json.dumps(list(DDGS().text(query, max_results=3)))

    return create_react_agent(_get_model(), tools=[web_search])


def make_nexum_agent(session_id: str):
    from submit_task import submit_tool_call

    @tool
    def web_search(query: str) -> str:
        """Search the web. Args: query: Search query."""
        return submit_tool_call("web_search", {"query": query, "max_results": 3}, session_id=session_id)

    return create_react_agent(_get_model(), tools=[web_search])


def run_timed(agent, query: str) -> float:
    t0 = time.perf_counter()
    agent.invoke({"messages": [("human", query)]})
    return time.perf_counter() - t0


def print_section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def main():
    print(f"\nLangGraph + Nexum Benchmark")
    print(f"Query: {QUERY[:60]}...")

    print_section("Scenario 1: Cold run")
    print("  Plain LangGraph...")
    try:
        plain_t1 = run_timed(make_plain_agent(), QUERY)
        print(f"  Plain: {plain_t1:.2f}s")
    except Exception as e:
        print(f"  Plain FAILED: {e}")
        plain_t1 = None

    print("  LangGraph + Nexum (cold)...")
    try:
        nexum_t1 = run_timed(make_nexum_agent("bench-cold"), QUERY)
        print(f"  Nexum (cold): {nexum_t1:.2f}s")
    except Exception as e:
        print(f"  Nexum FAILED: {e}")
        nexum_t1 = None

    if plain_t1 and nexum_t1:
        print(f"\n  Nexum overhead: {nexum_t1 - plain_t1:+.2f}s")

    print_section("Scenario 2: Re-run (Nexum caches tool results)")
    print("  Plain LangGraph (re-run, re-executes all tools)...")
    try:
        plain_t2 = run_timed(make_plain_agent(), QUERY)
        print(f"  Plain: {plain_t2:.2f}s")
    except Exception as e:
        plain_t2 = None

    print("  LangGraph + Nexum (cached tool results)...")
    try:
        nexum_t2 = run_timed(make_nexum_agent("bench-cold"), QUERY)
        print(f"  Nexum (cached): {nexum_t2:.2f}s ⚡")
    except Exception as e:
        nexum_t2 = None

    if plain_t2 and nexum_t2:
        print(f"\n  Speedup: {plain_t2 / nexum_t2:.1f}x faster")

    print_section("LangGraph Checkpointing vs Nexum Tool Cache")
    print("  LangGraph MemorySaver:")
    print("    ✓ Saves conversation state (messages)")
    print("    ✗ Tool calls re-execute on replay")
    print("    ✗ No exactly-once tool semantics")
    print()
    print("  LangGraph + Nexum:")
    print("    ✓ Tool results persisted in SQLite (exactly-once)")
    print("    ✓ Re-run same session → instant tool cache hits ⚡")
    print("    ✓ Crash after tool call 5? Resume from tool call 6")
    print()


if __name__ == "__main__":
    main()
