"""
benchmark.py - Compare plain Crawl4AI vs Crawl4AI+Nexum vs Nexum cached.

4-part benchmark:
  A) Plain Crawl4AI direct (asyncio.gather for 5 URLs)
  B) Nexum fresh (same 5 URLs via crawler.py, new session)
  C) Nexum cached (same 5 URLs, same session — all from DB)
  D) Crash sim — submit 5, crash after N, then re-run same session

Usage:
    PYTHONIOENCODING=utf-8 python benchmark.py
    PYTHONIOENCODING=utf-8 python benchmark.py --crash-after 2
"""

import argparse
import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from crawler import crawl_all, submit_crawl_url

URLS = [
    "https://www.rust-lang.org/",
    "https://go.dev/",
    "https://www.python.org/",
    "https://ziglang.org/",
    "https://www.typescriptlang.org/",
]


# -- Part A: Plain Crawl4AI ---------------------------------------------------

def run_part_a() -> dict:
    """Plain Crawl4AI direct crawl (asyncio.gather)."""
    results = {}

    try:
        from crawl4ai import AsyncWebCrawler, CacheMode

        async def crawl_direct():
            async with AsyncWebCrawler() as crawler:
                tasks = [
                    crawler.arun(url=url, cache_mode=CacheMode.BYPASS)
                    for url in URLS
                ]
                return await asyncio.gather(*tasks, return_exceptions=True)

        raw_results = asyncio.run(crawl_direct())
        for url, result in zip(URLS, raw_results):
            if isinstance(result, Exception):
                results[url] = {"success": False, "markdown": "", "error": str(result)}
            else:
                results[url] = {
                    "success": result.success,
                    "markdown": result.markdown[:50000] if result.markdown else "",
                    "status_code": result.status_code or 0,
                }
    except ImportError:
        # Crawl4AI not installed — fallback to httpx+BS4
        import httpx
        from bs4 import BeautifulSoup

        for url in URLS:
            try:
                resp = httpx.get(url, follow_redirects=True, timeout=30)
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)[:50000]
                results[url] = {"success": resp.status_code < 400, "markdown": text, "status_code": resp.status_code}
            except Exception as e:
                results[url] = {"success": False, "markdown": "", "error": str(e)}

    return results


# -- Part B: Nexum fresh -------------------------------------------------------

def run_part_b(session_prefix: str) -> dict:
    """Nexum fresh crawl (all URLs submitted in parallel)."""
    return crawl_all(URLS, session_prefix=session_prefix, max_workers=5)


# -- Part C: Nexum cached ------------------------------------------------------

def run_part_c(session_prefix: str) -> dict:
    """Nexum cached crawl (same session, all from DB)."""
    return crawl_all(URLS, session_prefix=session_prefix, max_workers=5)


# -- Part D: Crash simulation --------------------------------------------------

def run_part_d(crash_after: int) -> dict:
    """Crash sim: submit 5, crash after N, then re-run same session."""
    session = f"crash-sim-{uuid.uuid4().hex[:8]}"
    results_pass1 = {}

    print(f"\n  [Pass 1] Submitting {len(URLS)} URLs, crashing after {crash_after} complete...")
    completed = 0
    for url in URLS:
        try:
            result = submit_crawl_url(url, session_prefix=session, timeout=60)
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
    results_pass2 = crawl_all(URLS, session_prefix=session, max_workers=5)
    elapsed = time.perf_counter() - t0

    return {
        "pass1_completed": completed,
        "pass2_results": results_pass2,
        "pass2_elapsed": elapsed,
    }


# -- Main ----------------------------------------------------------------------

def _md_len(result: dict) -> int:
    if isinstance(result, dict):
        return len(result.get("markdown", ""))
    return 0


def _ok(result: dict) -> bool:
    if isinstance(result, dict):
        return result.get("success", False)
    return False


def main():
    parser = argparse.ArgumentParser(description="Crawl4AI + Nexum benchmark")
    parser.add_argument("--crash-after", type=int, default=2, help="Crash after N completions in Part D")
    args = parser.parse_args()

    timings = {}
    all_results = {}

    # Part A
    print("=" * 60)
    print("Part A: Plain Crawl4AI (direct)")
    print("=" * 60)
    t0 = time.perf_counter()
    all_results["A"] = run_part_a()
    timings["A"] = time.perf_counter() - t0
    print(f"  Elapsed: {timings['A']:.2f}s")

    # Part B
    session_b = f"bench-{uuid.uuid4().hex[:8]}"
    print()
    print("=" * 60)
    print("Part B: Nexum fresh")
    print("=" * 60)
    t0 = time.perf_counter()
    all_results["B"] = run_part_b(session_b)
    timings["B"] = time.perf_counter() - t0
    print(f"  Elapsed: {timings['B']:.2f}s")

    # Part C
    print()
    print("=" * 60)
    print("Part C: Nexum cached (same session)")
    print("=" * 60)
    t0 = time.perf_counter()
    all_results["C"] = run_part_c(session_b)
    timings["C"] = time.perf_counter() - t0
    print(f"  Elapsed: {timings['C']:.2f}s")

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
    print(f"{'Part':<8} {'Mode':<28} {'Time':>8} {'OK':>4} {'Fail':>6} {'Total chars':>12}")
    print("-" * 70)

    for part, label in [
        ("A", "Plain Crawl4AI"),
        ("B", "Nexum fresh"),
        ("C", "Nexum cached"),
        ("D", f"Crash recovery (after {args.crash_after})"),
    ]:
        results = all_results[part]
        ok_count = sum(1 for r in results.values() if _ok(r))
        fail_count = len(results) - ok_count
        total_chars = sum(_md_len(r) for r in results.values())
        t = timings[part]
        print(f"{part:<8} {label:<28} {t:>7.2f}s {ok_count:>4} {fail_count:>6} {total_chars:>12,}")

    print()
    if timings["C"] > 0 and timings["B"] > 0:
        speedup = timings["B"] / timings["C"]
        print(f"Cache speedup (B/C): {speedup:.1f}x")
    print(f"Crash recovery: {d_result['pass1_completed']}/{len(URLS)} cached, "
          f"pass 2 took {d_result['pass2_elapsed']:.2f}s")


if __name__ == "__main__":
    main()
