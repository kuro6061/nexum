"""
benchmark.py — Controlled overhead measurement for gpt-researcher retriever layer.

Compares DuckDuckGo searches three ways:
  A) Direct DDGS calls (baseline, no Nexum)
  B) Via Nexum EFFECT (fresh, no cache)
  C) Via Nexum EFFECT (all cached — crash recovery scenario)

Does NOT run full GPTResearcher (too slow for a benchmark).
Uses the same fixed queries as smolagents-nexum/benchmark_controlled.py.

Prerequisites:
    - Nexum server running: cargo run --bin nexum-server
    - smolagents-nexum worker running: python ../smolagents-nexum/worker.py

Usage:
    PYTHONIOENCODING=utf-8 python benchmark.py
"""

import os
import sys
import statistics
import time

# Make smolagents-nexum importable
_smolagents_dir = os.path.join(os.path.dirname(__file__), "..", "smolagents-nexum")
if _smolagents_dir not in sys.path:
    sys.path.insert(0, _smolagents_dir)

from submit_task import submit_tool_call  # noqa: E402

QUERIES = [
    "Rust programming language 2025 features",
    "Python 3.14 release date",
    "TypeScript 5.0 new features",
    "Go programming language updates 2025",
    "Zig programming language 2025",
]

DIVIDER = "=" * 60


def section(title):
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}")


def measure_direct(queries: list[str]) -> list[float]:
    """Part A: Direct DuckDuckGo calls via duckduckgo-search (no Nexum)."""
    from duckduckgo_search import DDGS

    ddg = DDGS()
    times = []
    for q in queries:
        t0 = time.time()
        results = list(ddg.text(q, region="wt-wt", max_results=5))
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  direct [{elapsed:.2f}s] '{q[:40]}...' -> {len(results)} results")
    return times


def measure_nexum(queries: list[str], session_id: str) -> list[float]:
    """Part B/C: DuckDuckGo searches via Nexum EFFECT."""
    times = []
    for q in queries:
        t0 = time.time()
        result = submit_tool_call("web_search", {"query": q}, session_id=session_id)
        elapsed = time.time() - t0
        times.append(elapsed)
        print(f"  nexum  [{elapsed:.2f}s] '{q[:40]}...' -> {len(result)} chars")
    return times


def fmt_stats(times: list[float]) -> str:
    return (
        f"total={sum(times):.2f}s  "
        f"avg={statistics.mean(times):.2f}s  "
        f"min={min(times):.2f}s  "
        f"max={max(times):.2f}s"
    )


def main():
    n = len(QUERIES)

    print(f"\n{'#' * 60}")
    print(f"  gpt-researcher Retriever Benchmark  ({n} fixed queries)")
    print(f"{'#' * 60}")

    # ── A. Direct DuckDuckGo ──────────────────────────────────────
    section(f"A. Direct DuckDuckGo ({n} queries, no Nexum)")
    direct_times = measure_direct(QUERIES)
    print(f"\n  {fmt_stats(direct_times)}")

    # ── B. Nexum fresh ────────────────────────────────────────────
    section(f"B. Nexum EFFECT ({n} queries, fresh — no cache)")
    nexum_times = measure_nexum(QUERIES, session_id="gptr-bench-fresh")
    print(f"\n  {fmt_stats(nexum_times)}")

    # ── C. Nexum cached ───────────────────────────────────────────
    section(f"C. Nexum EFFECT ({n} queries, all cached)")
    cached_times = measure_nexum(QUERIES, session_id="gptr-bench-fresh")
    print(f"\n  {fmt_stats(cached_times)}")

    # ── Summary table ─────────────────────────────────────────────
    section("SUMMARY")
    direct_avg = statistics.mean(direct_times)
    nexum_avg = statistics.mean(nexum_times)
    cached_avg = statistics.mean(cached_times)
    overhead = nexum_avg - direct_avg
    overhead_pct = overhead / direct_avg * 100 if direct_avg > 0 else 0
    speedup = direct_avg / cached_avg if cached_avg > 0 else float("inf")

    rows = [
        ("", "per call avg", f"total ({n} calls)"),
        ("\u2500" * 22, "\u2500" * 14, "\u2500" * 14),
        ("Direct (no Nexum)", f"{direct_avg:.2f}s", f"{sum(direct_times):.2f}s"),
        ("Nexum (fresh)", f"{nexum_avg:.2f}s", f"{sum(nexum_times):.2f}s"),
        ("Nexum (cached)", f"{cached_avg:.2f}s", f"{sum(cached_times):.2f}s"),
        ("\u2500" * 22, "\u2500" * 14, "\u2500" * 14),
        ("Overhead (fresh)", f"{overhead:+.2f}s ({overhead_pct:+.0f}%)", ""),
        ("Cache speedup", f"{speedup:.1f}x faster vs direct", ""),
    ]

    for label, col2, col3 in rows:
        print(f"  {label:<24} {col2:<22} {col3}")

    print()


if __name__ == "__main__":
    main()
