"""
benchmark.py - Before/After comparison: plain AutoGen vs AutoGen + Nexum

Demonstrates:
1. Normal run: both approaches work, Nexum adds small overhead
2. Crash scenario: plain AutoGen loses all progress; Nexum resumes from checkpoint
3. Repeated run: plain AutoGen re-executes everything; Nexum returns cached results instantly

Usage:
    GEMINI_API_KEY=... PYTHONIOENCODING=utf-8 python benchmark.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from ddgs import DDGS

QUERY = "What are the main differences between Python asyncio and threading?"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
DIVIDER = "=" * 65

# ── Plain AutoGen tool (direct execution, no Nexum) ─────────────────

_crash_counter = [0]
_crash_after: int | None = None


def web_search_direct(query: str) -> str:
    """Search the web directly (no durability)."""
    global _crash_counter, _crash_after
    _crash_counter[0] += 1
    if _crash_after is not None and _crash_counter[0] > _crash_after:
        raise RuntimeError("[CRASH] Process died mid-run! All progress lost.")
    ddg = DDGS()
    results = list(ddg.text(query, max_results=5))
    return json.dumps(results[:3])


def make_agent(tool_fn, label: str) -> AssistantAgent:
    model = OpenAIChatCompletionClient(
        model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key=GEMINI_KEY,
        model_capabilities={
            "vision": False,
            "function_calling": True,
            "json_output": True,
        },
    )
    from autogen_agentchat.tools import FunctionTool
    tool = FunctionTool(tool_fn, name="web_search", description="Search the web.")
    return AssistantAgent(label, model_client=model, tools=[tool])


# ── Scenario 1: Normal run ───────────────────────────────────────────

async def run_plain_autogen(query: str) -> tuple[str, float]:
    """Run plain AutoGen (no Nexum)."""
    global _crash_counter
    _crash_counter = [0]
    agent = make_agent(web_search_direct, "PlainAgent")
    t0 = time.perf_counter()
    from autogen_agentchat.messages import TextMessage
    from autogen_core import CancellationToken
    result = await agent.on_messages(
        [TextMessage(content=query, source="user")],
        cancellation_token=CancellationToken(),
    )
    elapsed = time.perf_counter() - t0
    return result.chat_message.content, elapsed


async def run_nexum_autogen(query: str, session_id: str | None = None) -> tuple[str, float]:
    """Run AutoGen with Nexum-backed tool calls."""
    from submit_task import submit_tool_call

    async def web_search_nexum(query: str) -> str:
        return await asyncio.to_thread(submit_tool_call, "web_search", {"query": query, "max_results": 5}, session_id=session_id)

    agent = make_agent(web_search_nexum, "NexumAgent")
    t0 = time.perf_counter()
    from autogen_agentchat.messages import TextMessage
    from autogen_core import CancellationToken
    result = await agent.on_messages(
        [TextMessage(content=query, source="user")],
        cancellation_token=CancellationToken(),
    )
    elapsed = time.perf_counter() - t0
    return result.chat_message.content, elapsed


# ── Helpers ──────────────────────────────────────────────────────────

def print_section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def print_result(label: str, elapsed: float, cached: bool = False):
    tag = " (cached ⚡)" if cached else ""
    print(f"  {label:<25} {elapsed:.2f}s{tag}")


# ── Main benchmark ───────────────────────────────────────────────────

async def main():
    if not GEMINI_KEY:
        print("ERROR: Set GEMINI_API_KEY env var")
        sys.exit(1)

    print(f"\nNexum + AutoGen Benchmark")
    print(f"Query: {QUERY[:60]}...")

    # ── Scenario 1: Normal run ───────────────────────────────────────
    print_section("Scenario 1: Normal run (first time)")

    print("  Running plain AutoGen...")
    try:
        _, plain_t = await run_plain_autogen(QUERY)
        print_result("Plain AutoGen", plain_t)
    except Exception as e:
        print(f"  Plain AutoGen FAILED: {e}")
        plain_t = None

    print("  Running AutoGen + Nexum (cold)...")
    try:
        _, nexum_t = await run_nexum_autogen(QUERY, session_id="bench-cold")
        print_result("AutoGen + Nexum (cold)", nexum_t)
    except Exception as e:
        print(f"  AutoGen + Nexum FAILED: {e}")
        nexum_t = None

    if plain_t and nexum_t:
        overhead = nexum_t - plain_t
        print(f"\n  Nexum overhead (first run): +{overhead:.2f}s")

    # ── Scenario 2: Repeated run (cached) ────────────────────────────
    print_section("Scenario 2: Re-run same query (Nexum uses cache)")

    print("  Running plain AutoGen (re-run)...")
    try:
        _, plain_t2 = await run_plain_autogen(QUERY)
        print_result("Plain AutoGen (re-run)", plain_t2)
    except Exception as e:
        print(f"  Plain AutoGen FAILED: {e}")
        plain_t2 = None

    print("  Running AutoGen + Nexum (cached)...")
    try:
        _, nexum_t2 = await run_nexum_autogen(QUERY, session_id="bench-cold")
        print_result("AutoGen + Nexum (cached)", nexum_t2, cached=True)
    except Exception as e:
        print(f"  AutoGen + Nexum FAILED: {e}")
        nexum_t2 = None

    if plain_t2 and nexum_t2:
        speedup = plain_t2 / nexum_t2
        print(f"\n  Nexum speedup on re-run: {speedup:.1f}x faster")

    # ── Summary ──────────────────────────────────────────────────────
    print_section("Summary")
    print("  Plain AutoGen:")
    print("    - No persistence: crash = start over")
    print("    - Re-run = full re-execution")
    print()
    print("  AutoGen + Nexum:")
    print("    - Tool results persisted atomically in SQLite")
    print("    - Crash = resume from last completed tool call")
    print("    - Re-run = instant cache hit ⚡")
    print()
    print(f"  See crash recovery demo: python crash_demo.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())
