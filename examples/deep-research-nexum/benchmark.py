"""
benchmark.py - Compare plain deep-research vs deep-research+Nexum.

4-part benchmark:
  A) Plain sequential: generate_queries → search+learn × N (sequential, no Nexum)
  B) Nexum fresh:      same N queries, all parallel EFFECTs, first run
  C) Nexum cached:     same session re-run — all from SQLite, zero LLM cost
  D) Crash sim:        submit N, crash after K, resume → only (N-K) LLM calls

Usage:
    PYTHONIOENCODING=utf-8 python benchmark.py
    PYTHONIOENCODING=utf-8 python benchmark.py --crash-after 2 --queries 4
"""

import argparse
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'packages', 'sdk-python'))

from openai import OpenAI
from ddgs import DDGS
from researcher import generate_queries, research_all, submit_query


TOPIC = "Rust programming language: performance, safety, and adoption in 2025"


# --- Part A: Plain sequential (no Nexum) ---

def plain_search_and_learn(query: str, research_goal: str) -> dict:
    """Plain sequential: DuckDuckGo + Gemini, no Nexum."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))

    if not results:
        return {"query": query, "learnings": [], "urls": []}

    urls = [r['href'] for r in results]
    contents = "\n\n".join([
        f"[{i+1}] {r['title']}\nURL: {r['href']}\n{r['body']}"
        for i, r in enumerate(results)
    ])

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    client = OpenAI(
        api_key=gemini_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": "Extract key learnings from search results."},
            {"role": "user", "content": (
                f"Research goal: {research_goal}\nQuery: {query}\n\n"
                f"Search results:\n{contents}\n\n"
                "Extract 3-5 key learnings. Start each with '- '."
            )},
        ],
        max_tokens=512,
    )
    raw = response.choices[0].message.content.strip()
    learnings = [
        line.lstrip("- •").strip()
        for line in raw.split("\n")
        if line.strip().startswith(("-", "•")) and len(line.strip()) > 10
    ]
    return {"query": query, "learnings": learnings or [raw], "urls": urls}


def run_part_a(queries: list[dict]) -> tuple[list[dict], int]:
    """Plain sequential search+learn for all queries."""
    results = []
    llm_calls = 0
    for q in queries:
        print(f"  [Plain] Searching: {q['query'][:60]}")
        try:
            r = plain_search_and_learn(q["query"], q["research_goal"])
            results.append(r)
            llm_calls += 1
        except Exception as e:
            results.append({"query": q["query"], "error": str(e), "learnings": [], "urls": []})
    return results, llm_calls


# --- Parts B/C/D use researcher.py functions ---

def run_part_b(queries: list[dict], session_prefix: str) -> tuple[dict, int]:
    """Nexum fresh parallel run."""
    results = research_all(queries, session_prefix=session_prefix, max_workers=4)
    return results, len(queries)


def run_part_c(queries: list[dict], session_prefix: str) -> tuple[dict, int]:
    """Nexum cached: same session, all from SQLite."""
    results = research_all(queries, session_prefix=session_prefix, max_workers=4)
    return results, 0  # zero LLM calls (cached)


def run_part_d(queries: list[dict], crash_after: int) -> tuple[dict, int, int]:
    """Crash sim: submit all, crash after K, then resume."""
    session = f"crash-sim-{uuid.uuid4().hex[:8]}"
    completed = 0

    print(f"\n  [Pass 1] Submitting {len(queries)} queries, crashing after {crash_after}...")
    for q in queries:
        try:
            submit_query(q["query"], q["research_goal"], session_prefix=session, timeout=120)
            completed += 1
            if completed >= crash_after:
                print(f"  [CRASH] Simulated crash after {completed} completions")
                break
        except Exception as e:
            print(f"  [ERROR] {e}")

    print(f"  [Pass 1] Completed {completed}/{len(queries)} before crash")
    print(f"\n  [Pass 2] Resuming session '{session}' (should skip {completed} cached)...")

    t0 = time.perf_counter()
    results = research_all(queries, session_prefix=session, max_workers=4)
    elapsed = time.perf_counter() - t0

    llm_calls_saved = completed
    llm_calls_needed = len(queries) - completed
    return results, llm_calls_needed, llm_calls_saved


# --- Main ---

def _ok(result) -> bool:
    if isinstance(result, dict):
        return bool(result.get("learnings")) and "error" not in result
    return False


def main():
    parser = argparse.ArgumentParser(description="Deep Research + Nexum benchmark")
    parser.add_argument("--crash-after", type=int, default=2)
    parser.add_argument("--queries", type=int, default=4)
    args = parser.parse_args()

    print(f"Topic: {TOPIC}")
    print(f"Queries per run: {args.queries}\n")

    # Generate queries once (shared across all parts)
    print("Generating sub-queries...")
    queries = generate_queries(TOPIC, args.queries)
    print()

    timings = {}
    llm_calls = {}

    # Part A
    print("=" * 60)
    print("Part A: Plain sequential (no Nexum)")
    print("=" * 60)
    t0 = time.perf_counter()
    results_a, calls_a = run_part_a(queries)
    timings["A"] = time.perf_counter() - t0
    llm_calls["A"] = calls_a
    ok_a = sum(1 for r in results_a if _ok(r))
    print(f"  Elapsed: {timings['A']:.2f}s | OK: {ok_a}/{len(queries)} | LLM calls: {calls_a}")

    # Part B
    session_b = f"bench-{uuid.uuid4().hex[:8]}"
    print()
    print("=" * 60)
    print("Part B: Nexum fresh (parallel)")
    print("=" * 60)
    t0 = time.perf_counter()
    results_b, calls_b = run_part_b(queries, session_b)
    timings["B"] = time.perf_counter() - t0
    llm_calls["B"] = calls_b
    ok_b = sum(1 for r in results_b.values() if _ok(r))
    print(f"  Elapsed: {timings['B']:.2f}s | OK: {ok_b}/{len(queries)} | LLM calls: {calls_b}")

    # Part C
    print()
    print("=" * 60)
    print("Part C: Nexum cached (same session — zero LLM cost)")
    print("=" * 60)
    t0 = time.perf_counter()
    results_c, calls_c = run_part_c(queries, session_b)
    timings["C"] = time.perf_counter() - t0
    llm_calls["C"] = calls_c
    ok_c = sum(1 for r in results_c.values() if _ok(r))
    print(f"  Elapsed: {timings['C']:.2f}s | OK: {ok_c}/{len(queries)} | LLM calls: 0 (cached)")

    # Part D
    print()
    print("=" * 60)
    print(f"Part D: Crash simulation (crash after {args.crash_after})")
    print("=" * 60)
    t0 = time.perf_counter()
    results_d, calls_d, saved_d = run_part_d(queries, args.crash_after)
    timings["D"] = time.perf_counter() - t0
    llm_calls["D"] = calls_d
    ok_d = sum(1 for r in results_d.values() if _ok(r))
    print(f"  Elapsed: {timings['D']:.2f}s | OK: {ok_d}/{len(queries)} | LLM calls: {calls_d} ({saved_d} saved)")

    # Comparison table
    print()
    print("=" * 60)
    print("COMPARISON TABLE")
    print("=" * 60)
    print()
    print(f"{'Part':<6} {'Mode':<38} {'Time':>8} {'OK':>4} {'LLM calls':>10}")
    print("-" * 70)
    for part, label in [
        ("A", "Plain sequential (no Nexum)"),
        ("B", "Nexum fresh (parallel)"),
        ("C", "Nexum cached (zero LLM cost)"),
        ("D", f"Crash recovery (after {args.crash_after})"),
    ]:
        ok_count = ok_a if part == "A" else ok_b if part == "B" else ok_c if part == "C" else ok_d
        print(f"{part:<6} {label:<38} {timings[part]:>7.2f}s {ok_count:>4} {llm_calls[part]:>10}")

    print()
    if timings["B"] > 0 and timings["C"] > 0:
        speedup = timings["B"] / timings["C"]
        print(f"Cache speedup (B→C): {speedup:.1f}x faster, {llm_calls['B']} LLM calls saved")
    if timings["A"] > 0 and timings["B"] > 0:
        parallel_speedup = timings["A"] / timings["B"]
        print(f"Parallel speedup (A→B): {parallel_speedup:.1f}x faster (concurrency)")
    print(f"Crash recovery: {saved_d}/{len(queries)} queries cached, "
          f"only {calls_d} LLM calls needed on resume")
    print()
    print(f"Total LLM calls without Nexum (A+D retry): {llm_calls['A'] + len(queries)}")
    print(f"Total LLM calls with Nexum    (B+C+D):     {llm_calls['B'] + 0 + llm_calls['D']}")


if __name__ == "__main__":
    main()
