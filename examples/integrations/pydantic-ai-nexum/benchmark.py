"""
benchmark.py — Plain Pydantic AI vs Pydantic AI + Nexum timing comparison.

Measures:
  1. Cold run: both approaches, compare overhead
  2. Re-run: plain re-executes all tools; Nexum returns cached results ⚡

Usage:
    GEMINI_API_KEY=... python benchmark.py
"""

import os
import sys
import time

from pydantic_ai import Agent

QUERY = "What are the key differences between asyncio and threading in Python?"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
DIVIDER = "=" * 60

if not GEMINI_KEY and not OPENAI_KEY:
    print("ERROR: Set GEMINI_API_KEY or OPENAI_API_KEY")
    sys.exit(1)

MODEL = "google-gla:gemini-2.0-flash" if GEMINI_KEY else "openai:gpt-4o-mini"


# ── Plain Pydantic AI (direct execution, no Nexum) ──────────────────────────

def make_plain_agent() -> Agent:
    from ddgs import DDGS

    agent = Agent(MODEL, system_prompt="You are a research assistant.")

    @agent.tool_plain
    def web_search(query: str) -> str:
        """Search the web."""
        results = list(DDGS().text(query, max_results=3))
        import json
        return json.dumps(results[:3])

    return agent


# ── Pydantic AI + Nexum ─────────────────────────────────────────────────────

def make_nexum_agent(session_id: str) -> Agent:
    from submit_task import submit_tool_call

    agent = Agent(MODEL, system_prompt="You are a research assistant.")

    @agent.tool_plain
    def web_search(query: str) -> str:
        """Search the web."""
        return submit_tool_call("web_search", {"query": query, "max_results": 3}, session_id=session_id)

    return agent


# ── Benchmark ────────────────────────────────────────────────────────────────

def print_section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def run_timed(agent: Agent, query: str) -> float:
    t0 = time.perf_counter()
    agent.run_sync(query)
    return time.perf_counter() - t0


def main():
    print(f"\nPydantic AI + Nexum Benchmark")
    print(f"Query: {QUERY[:60]}...")
    print(f"Model: {MODEL}")

    # ── Scenario 1: Cold run ─────────────────────────────────────────────────
    print_section("Scenario 1: Cold run")

    print("  Running plain Pydantic AI...")
    try:
        plain_t1 = run_timed(make_plain_agent(), QUERY)
        print(f"  Plain: {plain_t1:.2f}s")
    except Exception as e:
        print(f"  Plain FAILED: {e}")
        plain_t1 = None

    print("  Running Pydantic AI + Nexum (cold)...")
    try:
        nexum_t1 = run_timed(make_nexum_agent("bench-cold"), QUERY)
        print(f"  Nexum (cold): {nexum_t1:.2f}s")
    except Exception as e:
        print(f"  Nexum FAILED: {e}")
        nexum_t1 = None

    if plain_t1 and nexum_t1:
        print(f"\n  Nexum overhead (cold): +{nexum_t1 - plain_t1:+.2f}s")

    # ── Scenario 2: Re-run (cached) ──────────────────────────────────────────
    print_section("Scenario 2: Re-run same query (Nexum uses cache)")

    print("  Running plain Pydantic AI (re-run)...")
    try:
        plain_t2 = run_timed(make_plain_agent(), QUERY)
        print(f"  Plain (re-run): {plain_t2:.2f}s")
    except Exception as e:
        print(f"  Plain FAILED: {e}")
        plain_t2 = None

    print("  Running Pydantic AI + Nexum (cached)...")
    try:
        nexum_t2 = run_timed(make_nexum_agent("bench-cold"), QUERY)
        print(f"  Nexum (cached): {nexum_t2:.2f}s ⚡")
    except Exception as e:
        print(f"  Nexum FAILED: {e}")
        nexum_t2 = None

    if plain_t2 and nexum_t2:
        speedup = plain_t2 / nexum_t2
        print(f"\n  Nexum speedup on re-run: {speedup:.1f}x faster")

    # ── Summary ──────────────────────────────────────────────────────────────
    print_section("Summary")
    print("  Plain Pydantic AI:")
    print("    - No persistence: crash = start over")
    print("    - Re-run = full re-execution of all tool calls")
    print()
    print("  Pydantic AI + Nexum:")
    print("    - Tool results persisted atomically in SQLite")
    print("    - Crash = resume from last completed tool call")
    print("    - Re-run = instant cache hit ⚡")
    print()


if __name__ == "__main__":
    main()
