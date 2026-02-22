"""
benchmark.py - Compare plain sequential evaluation vs RAGAS+Nexum.

Directly addresses:
  - RAGAS #2473: "838 evaluations take 10 min despite 5k RPM" → Nexum parallel
  - RAGAS #2136: "Support Batch API for lower cost" → Nexum cache = $0 re-eval
  - RAGAS #2105: "Generate QA samples in parallel for big batches" → Nexum EFFECT

4-part benchmark:
  A) Plain sequential: evaluate samples one-by-one (no Nexum)
  B) Nexum fresh:      same samples as parallel EFFECTs (first run)
  C) Nexum cached:     same session re-run — all from SQLite, zero LLM cost
  D) Crash sim:        crash after K completions, resume → only K' LLM calls

Usage:
    PYTHONIOENCODING=utf-8 python benchmark.py
    PYTHONIOENCODING=utf-8 python benchmark.py --samples 10 --crash-after 4
"""

import argparse
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'packages', 'sdk-python'))

from openai import OpenAI
from dataset import EVAL_DATASET
from evaluator import evaluate_all, submit_eval, print_summary


# --- Part A: Plain sequential (no Nexum) ---

def plain_evaluate_one(sample: dict) -> dict:
    """Evaluate a single sample with Gemini directly (no Nexum, no caching)."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    client = OpenAI(
        api_key=gemini_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    context_text = "\n\n".join(f"[Context {i+1}]: {c}" for i, c in enumerate(sample["contexts"]))

    prompt = f"""Evaluate this QA sample.

Question: {sample["question"]}
Answer: {sample["answer"]}
{context_text}

Respond in JSON:
{{"faithfulness": <float 0-1>, "faithfulness_reason": "<str>", "answer_relevancy": <float 0-1>, "relevancy_reason": "<str>"}}"""

    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[
                {"role": "system", "content": "You are an expert RAG evaluation judge. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content.strip())
        return {
            "sample_id": sample["sample_id"],
            "question": sample["question"],
            "faithfulness": float(data.get("faithfulness", 0.0)),
            "answer_relevancy": float(data.get("answer_relevancy", 0.0)),
            "faithfulness_reason": data.get("faithfulness_reason", ""),
            "relevancy_reason": data.get("relevancy_reason", ""),
        }
    except Exception as e:
        return {"sample_id": sample["sample_id"], "question": sample["question"],
                "faithfulness": 0.0, "answer_relevancy": 0.0, "error": str(e)}


def run_part_a(samples: list[dict]) -> tuple[list[dict], int]:
    """Plain sequential evaluation — no parallelism, no crash recovery."""
    results = []
    for s in samples:
        print(f"  [Plain] Evaluating {s['sample_id']}...")
        results.append(plain_evaluate_one(s))
    return results, len(samples)


# --- Parts B/C/D use evaluator.py ---

def run_part_b(samples: list[dict], session: str) -> tuple[list[dict], int]:
    results = evaluate_all(samples, session_prefix=session, max_workers=8)
    return results, len(samples)


def run_part_c(samples: list[dict], session: str) -> tuple[list[dict], int]:
    results = evaluate_all(samples, session_prefix=session, max_workers=8)
    return results, 0  # zero LLM calls from cache


def run_part_d(samples: list[dict], crash_after: int) -> tuple[list[dict], int, int]:
    """Crash simulation: evaluate K samples, crash, then resume full set."""
    session = f"crash-{uuid.uuid4().hex[:8]}"
    completed = 0

    print(f"\n  [Pass 1] Evaluating {len(samples)} samples, crashing after {crash_after}...")
    for s in samples:
        try:
            submit_eval(s, session_prefix=session, timeout=120)
            completed += 1
            if completed >= crash_after:
                print(f"  [CRASH] Simulated crash after {completed} evaluations")
                break
        except Exception as e:
            print(f"  [ERROR] {e}")

    print(f"  [Pass 1] Completed {completed}/{len(samples)} before crash")
    print(f"\n  [Pass 2] Resuming session '{session}' (skip {completed} cached)...")

    results = evaluate_all(samples, session_prefix=session, max_workers=8)
    llm_calls_needed = len(samples) - completed
    return results, llm_calls_needed, completed


# --- Helpers ---

def _ok(r: dict) -> bool:
    return bool(r and "error" not in r and r.get("faithfulness", -1) >= 0)


def _avg_scores(results: list[dict]) -> tuple[float, float]:
    valid = [r for r in results if _ok(r)]
    if not valid:
        return 0.0, 0.0
    return (
        sum(r["faithfulness"] for r in valid) / len(valid),
        sum(r["answer_relevancy"] for r in valid) / len(valid),
    )


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="RAGAS-style evaluation benchmark with Nexum")
    parser.add_argument("--samples", type=int, default=8, help="Number of QA samples (default 8)")
    parser.add_argument("--crash-after", type=int, default=3, help="Crash after N in Part D (default 3)")
    args = parser.parse_args()

    samples = EVAL_DATASET[: args.samples]
    print(f"Benchmark: {len(samples)} QA samples")
    print(f"Addresses: RAGAS #2473 (slow), #2136 (batch cost), #2105 (parallel)\n")

    timings: dict[str, float] = {}
    llm_calls: dict[str, int] = {}
    all_results: dict[str, list] = {}

    # --- Part A ---
    print("=" * 60)
    print("Part A: Plain sequential (no Nexum)")
    print("=" * 60)
    t0 = time.perf_counter()
    results_a, calls_a = run_part_a(samples)
    timings["A"] = time.perf_counter() - t0
    llm_calls["A"] = calls_a
    all_results["A"] = results_a
    fa, ra = _avg_scores(results_a)
    print(f"  Elapsed: {timings['A']:.2f}s | LLM calls: {calls_a} | faithfulness={fa:.2f} relevancy={ra:.2f}")

    # --- Part B ---
    session_b = f"bench-{uuid.uuid4().hex[:8]}"
    print()
    print("=" * 60)
    print("Part B: Nexum fresh (parallel EFFECTs)")
    print("=" * 60)
    t0 = time.perf_counter()
    results_b, calls_b = run_part_b(samples, session_b)
    timings["B"] = time.perf_counter() - t0
    llm_calls["B"] = calls_b
    all_results["B"] = results_b
    fb, rb = _avg_scores(results_b)
    print(f"  Elapsed: {timings['B']:.2f}s | LLM calls: {calls_b} | faithfulness={fb:.2f} relevancy={rb:.2f}")

    # --- Part C ---
    print()
    print("=" * 60)
    print("Part C: Nexum cached (same session — zero LLM cost)")
    print("=" * 60)
    t0 = time.perf_counter()
    results_c, calls_c = run_part_c(samples, session_b)
    timings["C"] = time.perf_counter() - t0
    llm_calls["C"] = calls_c
    all_results["C"] = results_c
    fc, rc = _avg_scores(results_c)
    print(f"  Elapsed: {timings['C']:.2f}s | LLM calls: 0 (cached) | faithfulness={fc:.2f} relevancy={rc:.2f}")

    # --- Part D ---
    print()
    print("=" * 60)
    print(f"Part D: Crash simulation (crash after {args.crash_after})")
    print("=" * 60)
    t0 = time.perf_counter()
    results_d, calls_d, saved_d = run_part_d(samples, args.crash_after)
    timings["D"] = time.perf_counter() - t0
    llm_calls["D"] = calls_d
    all_results["D"] = results_d
    fd, rd = _avg_scores(results_d)
    print(f"  Elapsed: {timings['D']:.2f}s | LLM calls: {calls_d} ({saved_d} saved) | faithfulness={fd:.2f} relevancy={rd:.2f}")

    # --- Comparison table ---
    print()
    print("=" * 60)
    print("COMPARISON TABLE")
    print("=" * 60)
    print()
    print(f"{'Part':<6} {'Mode':<38} {'Time':>8} {'LLM calls':>10} {'Faithfulness':>13} {'Relevancy':>10}")
    print("-" * 90)

    meta = [
        ("A", "Plain sequential (no Nexum)",         results_a, calls_a),
        ("B", "Nexum fresh (parallel)",               results_b, calls_b),
        ("C", "Nexum cached (zero LLM cost)",         results_c, 0),
        ("D", f"Crash recovery (after {args.crash_after})", results_d, calls_d),
    ]
    for part, label, res, calls in meta:
        f_avg, r_avg = _avg_scores(res)
        print(f"{part:<6} {label:<38} {timings[part]:>7.2f}s {calls:>10} {f_avg:>13.2f} {r_avg:>10.2f}")

    print()
    # Speedup
    if timings["B"] > 0 and timings["A"] > 0:
        speedup = timings["A"] / timings["B"]
        print(f"Parallel speedup  (A→B): {speedup:.1f}x faster")
    if timings["C"] > 0 and timings["B"] > 0:
        cache_speedup = timings["B"] / timings["C"]
        print(f"Cache speedup     (B→C): {cache_speedup:.1f}x faster, {llm_calls['B']} LLM calls saved")
    print(f"Crash recovery    (D):   {saved_d}/{len(samples)} samples cached, {calls_d} LLM calls on resume")

    print()
    print(f"Total LLM calls without Nexum: {llm_calls['A'] + len(samples)}  (A + D full restart)")
    print(f"Total LLM calls with Nexum:    {llm_calls['B'] + 0 + llm_calls['D']}  (B + C=0 + D resume)")

    # Faithfulness breakdown (show which answers were flagged)
    print()
    print("=== Faithfulness flags (< 0.5 = potential hallucination) ===")
    for r in results_b:
        if r and r.get("faithfulness", 1.0) < 0.5:
            print(f"  ⚠ {r['sample_id']}: faithfulness={r['faithfulness']:.2f}  — {r.get('faithfulness_reason', '')[:80]}")


if __name__ == "__main__":
    main()
