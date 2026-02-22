"""
evaluator.py - Run RAGAS-style LLM-as-Judge evaluations via Nexum.

Each QA sample is submitted as a parallel EFFECT node:
  - Crash recovery: completed evaluations survive crashes
  - Parallelism: all samples evaluated concurrently
  - Caching: same sample never calls LLM twice

Usage:
    PYTHONIOENCODING=utf-8 python evaluator.py [--samples N] [--session NAME]
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'packages', 'sdk-python'))

from pydantic import BaseModel
from nexum import workflow, NexumClient
from dataset import EVAL_DATASET


# --- Shared workflow definition (must match worker.py) ---

class EvalResult(BaseModel):
    sample_id: str
    question: str
    faithfulness: float
    answer_relevancy: float
    faithfulness_reason: str
    relevancy_reason: str


def _placeholder(ctx):
    raise RuntimeError("evaluate must be handled by worker.py")


eval_workflow = (
    workflow("ragas-eval")
    .effect("evaluate", EvalResult, handler=_placeholder, depends_on=[])
    .build()
)


# --- Session persistence ---

def _session_file(prefix: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f".session-{prefix}.json")


def _load_session(prefix: str) -> dict:
    path = _session_file(prefix)
    return json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else {}


def _save_session(prefix: str, data: dict) -> None:
    with open(_session_file(prefix), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _make_key(sample: dict) -> str:
    payload = sample["sample_id"] + sample["question"] + sample["answer"]
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# --- Core: submit one evaluation EFFECT ---

def submit_eval(sample: dict, session_prefix: str = "default", timeout: float = 120) -> dict:
    """Submit a single QA evaluation to Nexum. Returns cached result if already done."""
    key = _make_key(sample)
    session = _load_session(session_prefix)
    client = NexumClient()

    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("evaluate", {})
            print(f"[Nexum] {sample['sample_id']} cached [done]")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
            exec_id = None

    client.register_workflow(eval_workflow)

    if exec_id is None:
        exec_id = client.start_execution(
            eval_workflow.workflow_id,
            {
                "sample_id": sample["sample_id"],
                "question": sample["question"],
                "answer": sample["answer"],
                "contexts": sample["contexts"],
            },
            version_hash=eval_workflow.version_hash,
        )
        session[key] = exec_id
        _save_session(session_prefix, session)
        print(f"[Nexum] {sample['sample_id']} submitted ({exec_id[:12]}...)")

    deadline = time.time() + timeout
    fast_until = time.time() + 2.0
    last_log = 0.0

    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st == "COMPLETED":
            result = status["completedNodes"].get("evaluate", {})
            faith = result.get("faithfulness", 0.0)
            relev = result.get("answer_relevancy", 0.0)
            print(f"[Nexum] {sample['sample_id']} done  faithfulness={faith:.2f}  relevancy={relev:.2f}")
            client.close()
            return result
        if st in ("FAILED", "CANCELLED"):
            client.close()
            raise RuntimeError(f"Nexum execution {exec_id} {st}")

        now = time.time()
        if now - last_log >= 2.0:
            print(f"[Nexum] {sample['sample_id']} waiting ({st})...")
            last_log = now

        time.sleep(0.05 if time.time() < fast_until else 0.2)

    client.close()
    raise TimeoutError(f"Nexum execution {exec_id} timed out")


def evaluate_all(
    samples: list[dict],
    session_prefix: str = "default",
    max_workers: int = 8,
) -> list[dict]:
    """Submit all samples in parallel and collect results."""
    results = [None] * len(samples)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(submit_eval, s, session_prefix): i
            for i, s in enumerate(samples)
        }
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = {
                    "sample_id": samples[idx]["sample_id"],
                    "faithfulness": 0.0,
                    "answer_relevancy": 0.0,
                    "error": str(e),
                }
    return results


def print_summary(results: list[dict]) -> None:
    """Print evaluation summary table."""
    print()
    print(f"{'ID':<6} {'Faithfulness':>14} {'Relevancy':>10}  Question (truncated)")
    print("-" * 75)
    for r in results:
        if r is None:
            continue
        sid = r.get("sample_id", "?")
        faith = r.get("faithfulness", 0.0)
        relev = r.get("answer_relevancy", 0.0)
        q = r.get("question", "")[:42]
        flag = "⚠" if faith < 0.5 else " "
        print(f"{sid:<6} {faith:>14.2f} {relev:>10.2f}  {flag} {q}")

    valid = [r for r in results if r and "error" not in r]
    if valid:
        avg_faith = sum(r["faithfulness"] for r in valid) / len(valid)
        avg_relev = sum(r["answer_relevancy"] for r in valid) / len(valid)
        print("-" * 75)
        print(f"{'AVG':<6} {avg_faith:>14.2f} {avg_relev:>10.2f}  ({len(valid)} samples)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAGAS-style evaluation with Nexum")
    parser.add_argument("--samples", type=int, default=len(EVAL_DATASET))
    parser.add_argument("--session", type=str, default="cli")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    samples = EVAL_DATASET[: args.samples]
    print(f"Evaluating {len(samples)} QA samples  session={args.session}  workers={args.workers}\n")

    t0 = time.perf_counter()
    results = evaluate_all(samples, session_prefix=args.session, max_workers=args.workers)
    elapsed = time.perf_counter() - t0

    print_summary(results)
    print(f"\nTotal time: {elapsed:.2f}s  ({len(samples)} samples, {args.workers} workers)")
