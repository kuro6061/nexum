"""
benchmark_controlled.py  EControlled overhead measurement

LLM エージェント�E毎回違うパスを取る�Eでフェアな比輁E��難しい、Eこ�Eスクリプトは固宁EN 回�EチE�Eル呼び出しを直接測定する、ELLM を介さず、直接 submit_tool_call() vs DuckDuckGoSearchTool() を比輁E��E
Usage:
    GEMINI_API_KEY=... PYTHONIOENCODING=utf-8 python benchmark_controlled.py
"""

import os
import sys
import time
import statistics


from smolagents import DuckDuckGoSearchTool
from submit_task import submit_tool_call

QUERIES = [
    "Rust programming language 2025 features",
    "Python 3.14 release date",
    "TypeScript 5.0 new features",
    "Go programming language updates 2025",
    "Zig programming language 2025",
]

DIVIDER = "=" * 60

def section(t): print(f"\n{DIVIDER}\n  {t}\n{DIVIDER}")


def measure_plain(queries: list[str]) -> list[float]:
    """Direct DuckDuckGo calls (no Nexum)."""
    tool = DuckDuckGoSearchTool()
    times = []
    for q in queries:
        t0 = time.time()
        result = tool(q)
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  plain [{elapsed:.2f}s] '{q[:40]}...' -> {len(result)} chars")
    return times


def measure_nexum(queries: list[str], session_id: str = "benchmark") -> list[float]:
    """Nexum-backed calls (gRPC + worker)."""
    times = []
    for q in queries:
        t0 = time.time()
        result = submit_tool_call("web_search", {"query": q}, session_id=session_id)
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  nexum [{elapsed:.2f}s] '{q[:40]}...' -> {len(result)} chars")
    return times


def measure_nexum_cached(queries: list[str], session_id: str = "benchmark") -> list[float]:
    """Nexum calls reusing a previous session (all cached)."""
    times = []
    for q in queries:
        t0 = time.time()
        result = submit_tool_call("web_search", {"query": q}, session_id=session_id)
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  cache [{elapsed:.2f}s] '{q[:40]}...' -> {len(result)} chars")
    return times


def stats(times: list[float]) -> str:
    return (
        f"total={sum(times):.2f}s  "
        f"avg={statistics.mean(times):.2f}s  "
        f"min={min(times):.2f}s  "
        f"max={max(times):.2f}s"
    )


def main():
    n = len(QUERIES)

    print(f"\n{'#'*60}")
    print(f"  Nexum Controlled Overhead Benchmark  ({n} fixed tool calls)")
    print(f"{'#'*60}")

    # ── 1. Plain ──────────────────────────────────────────────────
    section(f"1. Plain DuckDuckGo ({n} calls, no Nexum)")
    plain_times = measure_plain(QUERIES)
    plain_stats = stats(plain_times)
    print(f"\n  {plain_stats}")

    # ── 2. Nexum (first run, no cache) ───────────────────────────
    section(f"2. Nexum ({n} calls, fresh  Eno cache)")
    nexum_times = measure_nexum(QUERIES, session_id="bench-fresh")
    nexum_stats = stats(nexum_times)
    print(f"\n  {nexum_stats}")

    # ── 3. Nexum (second run, all cached) ────────────────────────
    section(f"3. Nexum ({n} calls, all cached  Ecrash-recovery demo)")
    cached_times = measure_nexum_cached(QUERIES, session_id="bench-fresh")
    cached_stats = stats(cached_times)
    print(f"\n  {cached_stats}")

    # ── Summary ───────────────────────────────────────────────────
    section("SUMMARY")
    plain_avg   = statistics.mean(plain_times)
    nexum_avg   = statistics.mean(nexum_times)
    cached_avg  = statistics.mean(cached_times)
    overhead    = nexum_avg - plain_avg
    overhead_pct= overhead / plain_avg * 100
    speedup     = plain_avg / cached_avg if cached_avg > 0 else float("inf")

    rows = [
        ("", "per call avg", "total (" + str(n) + " calls)"),
        ("─"*22, "─"*14, "─"*14),
        ("Plain (no Nexum)",   f"{plain_avg:.2f}s",  f"{sum(plain_times):.2f}s"),
        ("Nexum (fresh)",      f"{nexum_avg:.2f}s",  f"{sum(nexum_times):.2f}s"),
        ("Nexum (cached)",     f"{cached_avg:.2f}s", f"{sum(cached_times):.2f}s"),
        ("─"*22, "─"*14, "─"*14),
        ("Overhead (fresh)",   f"{overhead:+.2f}s ({overhead_pct:+.0f}%)", ""),
        ("Cache speedup",      f"{speedup:.1f}x faster vs plain", ""),
    ]

    for label, col2, col3 in rows:
        print(f"  {label:<24} {col2:<22} {col3}")

    print()


if __name__ == "__main__":
    main()
