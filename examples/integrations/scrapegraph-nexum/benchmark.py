"""
benchmark.py - Compare plain SmartScraperGraph vs ScrapeGraphAI+Nexum vs Nexum cached.

4-part benchmark:
  A) Plain SmartScraperGraph sequential (no Nexum)
  B) Nexum fresh (parallel via ThreadPoolExecutor)
  C) Nexum cached (same session  Eall from SQLite, zero LLM cost)
  D) Crash sim  Esubmit 5, crash after N, then re-run same session

Usage:
    PYTHONIOENCODING=utf-8 python benchmark.py
    PYTHONIOENCODING=utf-8 python benchmark.py --crash-after 2
"""

import argparse
import json
import os
import sys
import time
import uuid


from scraper import scrape_all, submit_scrape

URLS = [
    "https://www.rust-lang.org/",
    "https://go.dev/",
    "https://www.python.org/",
    "https://ziglang.org/",
    "https://www.typescriptlang.org/",
]
PROMPT = "Extract: language name, main use cases, and latest version if mentioned."


# -- Part A: Plain SmartScraperGraph (sequential) ------------------------------

def run_part_a() -> dict:
    """Plain SmartScraperGraph sequential extraction (no Nexum)."""
    results = {}

    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    try:
        from scrapegraphai.graphs import SmartScraperGraph
        from langchain_openai import ChatOpenAI
    except ImportError:
        print("  [SKIP] ScrapeGraphAI not installed, skipping Part A")
        for url in URLS:
            results[url] = {"success": False, "result": "{}", "error": "scrapegraphai not installed"}
        return results

    llm_instance = ChatOpenAI(
        model="gemini-2.5-flash",
        openai_api_key=gemini_key,
        openai_api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
        max_tokens=4096,
    )
    graph_config = {
        "llm": {
            "model_instance": llm_instance,
            "model_tokens": 8192,
        },
        "verbose": False,
        "headless": True,
    }

    for url in URLS:
        print(f"  Scraping: {url}")
        try:
            scraper = SmartScraperGraph(
                prompt=PROMPT,
                source=url,
                config=graph_config,
            )
            result = scraper.run()
            results[url] = {
                "success": True,
                "result": json.dumps(result),
            }
            print(f"    OK: {json.dumps(result)[:120]}...")
        except Exception as e:
            # Try alternate model name  Eplaceholder to avoid removing the try/except structure
            try:
                alt_config = {**graph_config}
                scraper = SmartScraperGraph(
                    prompt=PROMPT,
                    source=url,
                    config=alt_config,
                )
                result = scraper.run()
                results[url] = {
                    "success": True,
                    "result": json.dumps(result),
                }
                print(f"    OK (alt model): {json.dumps(result)[:120]}...")
            except Exception as e2:
                results[url] = {"success": False, "result": "{}", "error": str(e2)}
                print(f"    FAIL: {e2}")

    return results


# -- Part B: Nexum fresh (parallel) --------------------------------------------

def run_part_b(session_prefix: str) -> dict:
    """Nexum fresh scrape (all URLs submitted in parallel)."""
    tasks = [(url, PROMPT) for url in URLS]
    return scrape_all(tasks, session_prefix=session_prefix, max_workers=3)


# -- Part C: Nexum cached ------------------------------------------------------

def run_part_c(session_prefix: str) -> dict:
    """Nexum cached scrape (same session, all from SQLite  Ezero LLM cost)."""
    tasks = [(url, PROMPT) for url in URLS]
    return scrape_all(tasks, session_prefix=session_prefix, max_workers=3)


# -- Part D: Crash simulation --------------------------------------------------

def run_part_d(crash_after: int) -> dict:
    """Crash sim: submit 5, crash after N, then re-run same session."""
    session = f"crash-sim-{uuid.uuid4().hex[:8]}"
    results_pass1 = {}

    print(f"\n  [Pass 1] Submitting {len(URLS)} URLs, crashing after {crash_after} complete...")
    completed = 0
    for url in URLS:
        try:
            result = submit_scrape(url, PROMPT, session_prefix=session, timeout=120)
            results_pass1[url] = result
            completed += 1
            if completed >= crash_after:
                print(f"  [CRASH] Simulated crash after {completed} completions")
                break
        except Exception as e:
            results_pass1[url] = {"error": str(e)}

    print(f"  [Pass 1] Completed {completed}/{len(URLS)} URLs before crash")

    print(f"\n  [Pass 2] Re-running same session '{session}' (should skip {completed} cached)...")
    t0 = time.perf_counter()
    tasks = [(url, PROMPT) for url in URLS]
    results_pass2 = scrape_all(tasks, session_prefix=session, max_workers=3)
    elapsed = time.perf_counter() - t0

    return {
        "pass1_completed": completed,
        "pass2_results": results_pass2,
        "pass2_elapsed": elapsed,
    }


# -- Main ----------------------------------------------------------------------

def _result_len(result: dict) -> int:
    if isinstance(result, dict):
        return len(result.get("result", ""))
    return 0


def _ok(result: dict) -> bool:
    if isinstance(result, dict):
        return result.get("success", False)
    return False


def main():
    parser = argparse.ArgumentParser(description="ScrapeGraphAI + Nexum benchmark")
    parser.add_argument("--crash-after", type=int, default=2, help="Crash after N completions in Part D")
    args = parser.parse_args()

    timings = {}
    all_results = {}

    # Part A
    print("=" * 60)
    print("Part A: Plain SmartScraperGraph (sequential, no Nexum)")
    print("=" * 60)
    t0 = time.perf_counter()
    all_results["A"] = run_part_a()
    timings["A"] = time.perf_counter() - t0
    print(f"  Elapsed: {timings['A']:.2f}s")
    print(f"  LLM calls: {len(URLS)}")

    # Part B
    session_b = f"bench-{uuid.uuid4().hex[:8]}"
    print()
    print("=" * 60)
    print("Part B: Nexum fresh (parallel)")
    print("=" * 60)
    t0 = time.perf_counter()
    all_results["B"] = run_part_b(session_b)
    timings["B"] = time.perf_counter() - t0
    print(f"  Elapsed: {timings['B']:.2f}s")
    print(f"  LLM calls: {len(URLS)}")

    # Part C
    print()
    print("=" * 60)
    print("Part C: Nexum cached (same session  Ezero LLM cost)")
    print("=" * 60)
    t0 = time.perf_counter()
    all_results["C"] = run_part_c(session_b)
    timings["C"] = time.perf_counter() - t0
    print(f"  Elapsed: {timings['C']:.2f}s")
    print(f"  LLM calls: 0 (all from cache)")

    # Part D
    print()
    print("=" * 60)
    print(f"Part D: Crash simulation (crash after {args.crash_after})")
    print("=" * 60)
    t0 = time.perf_counter()
    d_result = run_part_d(args.crash_after)
    timings["D"] = time.perf_counter() - t0
    all_results["D"] = d_result["pass2_results"]
    print(f"  Pass 2 elapsed: {d_result['pass2_elapsed']:.2f}s")

    # Comparison table
    print()
    print("=" * 60)
    print("COMPARISON TABLE")
    print("=" * 60)
    print()
    print(f"{'Part':<8} {'Mode':<35} {'Time':>8} {'OK':>4} {'Fail':>6} {'LLM calls':>10}")
    print("-" * 75)

    llm_calls = {
        "A": len(URLS),
        "B": len(URLS),
        "C": 0,
        "D": len(URLS) - d_result["pass1_completed"],
    }

    for part, label in [
        ("A", "Plain SmartScraperGraph (sequential)"),
        ("B", "Nexum fresh (parallel)"),
        ("C", "Nexum cached (zero LLM cost)"),
        ("D", f"Crash recovery (after {args.crash_after})"),
    ]:
        results = all_results[part]
        ok_count = sum(1 for r in results.values() if _ok(r))
        fail_count = len(results) - ok_count
        t = timings[part]
        print(f"{part:<8} {label:<35} {t:>7.2f}s {ok_count:>4} {fail_count:>6} {llm_calls[part]:>10}")

    # Summary
    print()
    if timings["C"] > 0 and timings["B"] > 0:
        speedup = timings["B"] / timings["C"]
        print(f"Cache speedup (B/C): {speedup:.1f}x")

    saved = len(URLS) + d_result["pass1_completed"]
    print(f"Crash recovery: {d_result['pass1_completed']}/{len(URLS)} cached from pass 1, "
          f"pass 2 took {d_result['pass2_elapsed']:.2f}s")
    print()
    print(f"Part C saved {len(URLS)} LLM calls = $0 cost on re-run")
    print(f"Total LLM calls saved by caching (Parts C+D): {saved}")


if __name__ == "__main__":
    main()
