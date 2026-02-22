"""
benchmark.py — Plain OpenAI Agents vs OpenAI Agents + Nexum timing.

Usage:
    OPENAI_API_KEY=... python benchmark.py
"""

import asyncio
import os
import sys
import time

from agents import Agent, Runner, function_tool

QUERY = "What are the main differences between Python asyncio and threading?"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
DIVIDER = "=" * 60

if not OPENAI_KEY and not GEMINI_KEY:
    print("ERROR: Set OPENAI_API_KEY or GEMINI_API_KEY")
    sys.exit(1)

MODEL = "gpt-4o-mini" if OPENAI_KEY else "gemini/gemini-2.0-flash"


def make_plain_agent() -> Agent:
    import json
    from ddgs import DDGS

    @function_tool
    def web_search(query: str) -> str:
        """Search the web.
        Args:
            query: Search query.
        """
        return json.dumps(list(DDGS().text(query, max_results=3)))

    return Agent(
        name="PlainAgent",
        model=MODEL,
        instructions="You are a research assistant.",
        tools=[web_search],
    )


def make_nexum_agent(session_id: str) -> Agent:
    from submit_task import submit_tool_call

    @function_tool
    def web_search(query: str) -> str:
        """Search the web.
        Args:
            query: Search query.
        """
        return submit_tool_call("web_search", {"query": query, "max_results": 3}, session_id=session_id)

    return Agent(
        name="NexumAgent",
        model=MODEL,
        instructions="You are a research assistant.",
        tools=[web_search],
    )


async def run_timed(agent: Agent, query: str) -> float:
    t0 = time.perf_counter()
    await Runner.run(agent, query)
    return time.perf_counter() - t0


def print_section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


async def main():
    print(f"\nOpenAI Agents SDK + Nexum Benchmark")
    print(f"Model: {MODEL}")
    print(f"Query: {QUERY[:60]}...")

    print_section("Scenario 1: Cold run")
    print("  Plain agent...")
    try:
        plain_t1 = await run_timed(make_plain_agent(), QUERY)
        print(f"  Plain: {plain_t1:.2f}s")
    except Exception as e:
        print(f"  Plain FAILED: {e}")
        plain_t1 = None

    print("  Nexum agent (cold)...")
    try:
        nexum_t1 = await run_timed(make_nexum_agent("bench-cold"), QUERY)
        print(f"  Nexum (cold): {nexum_t1:.2f}s")
    except Exception as e:
        print(f"  Nexum FAILED: {e}")
        nexum_t1 = None

    if plain_t1 and nexum_t1:
        print(f"\n  Nexum overhead: +{nexum_t1 - plain_t1:+.2f}s")

    print_section("Scenario 2: Re-run (Nexum uses cache)")
    print("  Plain agent (re-run)...")
    try:
        plain_t2 = await run_timed(make_plain_agent(), QUERY)
        print(f"  Plain: {plain_t2:.2f}s")
    except Exception as e:
        plain_t2 = None

    print("  Nexum agent (cached)...")
    try:
        nexum_t2 = await run_timed(make_nexum_agent("bench-cold"), QUERY)
        print(f"  Nexum (cached): {nexum_t2:.2f}s ⚡")
    except Exception as e:
        nexum_t2 = None

    if plain_t2 and nexum_t2:
        print(f"\n  Speedup on re-run: {plain_t2 / nexum_t2:.1f}x faster")

    print_section("Summary")
    print("  Plain: no persistence, crash = restart from zero")
    print("  Nexum: SQLite-backed, crash = resume from last tool call ⚡")


if __name__ == "__main__":
    asyncio.run(main())
