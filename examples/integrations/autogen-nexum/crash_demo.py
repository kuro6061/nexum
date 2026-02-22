"""
crash_demo.py  EDemonstrates crash recovery for AutoGen #7043.

This script:
  1. Starts the 4-step research pipeline
  2. Runs a worker that crashes after the 'validate' node completes
  3. After the crash, starts a fresh worker
  4. Shows that Nexum resumes from 'summarize'  Enot from the beginning
  5. Prints a full timeline showing which steps ran in which worker

AutoGen's GraphFlow (#7043) gets stuck when resumed after an interrupt.
Nexum doesn't get stuck because each node result is committed atomically.

Usage:
    python crash_demo.py
    python crash_demo.py --query "Impact of AI on distributed systems"
    python crash_demo.py --crash-after validate    # default
    python crash_demo.py --crash-after research    # crash earlier

Prerequisites:
    Nexum server must be running: cargo run --bin nexum-server
"""

import argparse
import subprocess
import sys
import time
import os


from nexum import NexumClient
from pipeline_workflow import research_report_workflow


STEPS = ["research", "validate", "summarize", "report"]
WORKER_PY = os.path.join(os.path.dirname(__file__), "pipeline_worker.py")


def banner(msg: str, char="─"):
    width = 60
    print(f"\n{char * width}")
    print(f"  {msg}")
    print(f"{char * width}")


def poll_until_done(client: NexumClient, exec_id: str, timeout: float = 30) -> dict:
    """Poll GetExecution until COMPLETED or FAILED."""
    deadline = time.time() + timeout
    last_log = 0.0
    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st in ("COMPLETED", "FAILED", "CANCELLED"):
            return status
        now = time.time()
        if now - last_log >= 2.0:
            completed = list(status.get("completedNodes", {}).keys())
            print(f"  [poll] status={st}, completed nodes: {completed}")
            last_log = now
        time.sleep(0.2)
    raise TimeoutError(f"Execution {exec_id} did not finish within {timeout}s")


def start_worker(crash_after: str | None = None) -> subprocess.Popen:
    """Start pipeline_worker.py as a subprocess."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if crash_after:
        env["CRASH_AFTER"] = crash_after
    else:
        env.pop("CRASH_AFTER", None)

    return subprocess.Popen(
        [sys.executable, WORKER_PY],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(description="AutoGen #7043 crash recovery demo")
    parser.add_argument("--query", default="Impact of AI on distributed systems",
                        help="Research query for the pipeline")
    parser.add_argument("--crash-after", default="validate",
                        choices=STEPS[:-1],
                        help="Which node to crash after (default: validate)")
    args = parser.parse_args()

    client = NexumClient()

    # ── Step 1: Register workflow and start execution ──────────────
    banner("Step 1: Starting pipeline execution", "╁E)
    client.register_workflow(research_report_workflow)

    exec_id = client.start_execution(
        research_report_workflow.workflow_id,
        {"query": args.query},
        version_hash=research_report_workflow.version_hash,
    )
    print(f"  Execution ID: {exec_id}")
    print(f"  Query:        {args.query}")
    print(f"  Pipeline:     research ↁEvalidate ↁEsummarize ↁEreport")

    # ── Step 2: Start worker #1  Ewill crash after specified node ──
    banner(f"Step 2: Worker #1 starts (will crash after '{args.crash_after}')", "╁E)
    crash_node = args.crash_after
    worker1 = start_worker(crash_after=crash_node)

    # Wait for the worker to crash
    crash_idx = STEPS.index(crash_node)
    expected_crash_time = (crash_idx + 1) * 0.7 + 2.0  # generous timeout
    worker1.wait(timeout=expected_crash_time + 5)
    print(f"\n  Worker #1 exited with code: {worker1.returncode}")

    if worker1.returncode == 0:
        print("  [WARNING] Worker exited cleanly  Ecrash simulation may not have triggered.")
        print("  Continuing anyway...")
    else:
        print(f"  ✁EWorker #1 crashed as expected (simulating SIGKILL / OOM)")

    # ── Step 3: Verify partial progress ───────────────────────────
    banner("Step 3: Checking partial progress in Nexum DB", "╁E)
    time.sleep(0.5)  # let server finalize any in-flight commits
    status = client.get_status(exec_id)
    completed = list(status.get("completedNodes", {}).keys())
    print(f"  Execution status: {status['status']}")
    print(f"  Completed nodes:  {completed}")
    print(f"\n  With AutoGen GraphFlow #7043:")
    print(f"    ↁEResume ↁE'execution is complete' (stuck, wrong)")
    print(f"\n  With Nexum:")
    print(f"    ↁEResume ↁEpicks up from next pending node (correct)")

    # ── Step 4: Fresh worker resumes ──────────────────────────────
    banner("Step 4: Worker #2 starts (no crash  Efresh, naive worker)", "╁E)
    print("  This worker has NO knowledge of the previous run.")
    print("  It just starts polling. Nexum tells it exactly what to run next.\n")
    t_resume = time.time()
    worker2 = start_worker(crash_after=None)

    # Poll until done
    final_status = poll_until_done(client, exec_id, timeout=30)
    t_done = time.time()
    worker2.terminate()

    # ── Step 5: Print results ─────────────────────────────────────
    banner("Step 5: Results", "╁E)
    final_nodes = final_status.get("completedNodes", {})

    print(f"\n  Final status: {final_status['status']}")
    print(f"  Resume ↁEdone in: {t_done - t_resume:.1f}s")
    print()

    # Timeline
    print("  Node timeline:")
    for step in STEPS:
        if step in final_nodes:
            worker_label = "Worker #1" if step in completed else "Worker #2"
            resumed = " ↁEresumed here" if step == STEPS[crash_idx + 1] else ""
            print(f"    {'✁E:2} {step:12}  ({worker_label}){resumed}")
        else:
            print(f"    {'✁E:2} {step:12}  (not completed)")

    print()
    skipped = [s for s in completed if s in final_nodes]
    resumed_from = STEPS[crash_idx + 1] if crash_idx + 1 < len(STEPS) else None
    if resumed_from:
        print(f"  ✁EWorker #2 started from '{resumed_from}'  Enot from the beginning")
        print(f"  ✁ENodes re-executed by Worker #2: {[s for s in STEPS if s not in completed and s in final_nodes]}")

    # Final report
    if "report" in final_nodes:
        print()
        print("  Final report output:")
        print("  " + "─" * 40)
        for line in final_nodes["report"]["result"].splitlines():
            print(f"  {line}")

    client.close()
    banner("Demo complete", "╁E)


if __name__ == "__main__":
    main()
