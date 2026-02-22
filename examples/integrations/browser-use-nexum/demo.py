"""
demo.py — browser-use + Nexum: durable multi-step browser research pipeline.

Each step in the pipeline is a browser-use Agent.run() wrapped as a Nexum EFFECT.
If the process crashes mid-pipeline, it resumes from the last completed step.

Usage:
    # Terminal 1: Nexum server
    nexum dev

    # Terminal 2: Worker (runs browser-use)
    GEMINI_API_KEY=... python worker.py

    # Terminal 3: Start research
    python demo.py "durable execution for AI agents"

    # If it crashes, re-run with same execution ID
    python demo.py --resume <execution_id>
"""

import sys
import os
import time

from nexum import NexumClient
from worker import browser_research_workflow

GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")

if not GEMINI_KEY and not OPENAI_KEY:
    print("ERROR: Set GEMINI_API_KEY or OPENAI_API_KEY")
    sys.exit(1)


def run_research(topic: str) -> dict:
    client = NexumClient()
    client.register_workflow(browser_research_workflow)

    print(f"\n🔍 Starting browser research pipeline: {topic}")
    print("  Step 1: Research (browser-use)")
    print("  Step 2: Summarize (local)")
    print("  Step 3: Follow-up (browser-use)")
    print("  Step 4: Generate report (local)")
    print("\nNote: If this crashes, re-run with the same topic to resume ✓")
    print("-" * 60)

    exec_id = client.start_execution(
        browser_research_workflow.workflow_id,
        {"topic": topic},
        version_hash=browser_research_workflow.version_hash,
    )
    print(f"Execution: {exec_id}")

    deadline = time.time() + 600  # 10 min timeout
    last_status = ""
    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st != last_status:
            completed = list(status.get("completedNodes", {}).keys())
            if completed:
                print(f"  Completed steps: {', '.join(completed)}")
            last_status = st
        if st == "COMPLETED":
            print("\n✅ Research pipeline complete!")
            client.close()
            return status["completedNodes"]
        if st in ("FAILED", "CANCELLED"):
            client.close()
            raise RuntimeError(f"Pipeline {st}")
        time.sleep(2.0)

    client.close()
    raise TimeoutError(f"Pipeline timed out after 10 minutes")


def resume_research(exec_id: str) -> dict:
    """Resume a previously started pipeline."""
    client = NexumClient()
    print(f"\n🔄 Resuming execution: {exec_id}")
    print("  Already-completed steps will load from Nexum cache ⚡")
    print("-" * 60)

    deadline = time.time() + 600
    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st == "COMPLETED":
            print("\n✅ Research pipeline complete!")
            client.close()
            return status["completedNodes"]
        if st in ("FAILED", "CANCELLED"):
            client.close()
            raise RuntimeError(f"Pipeline {st}")
        completed = list(status.get("completedNodes", {}).keys())
        print(f"  Status: {st}, completed: {completed}")
        time.sleep(2.0)

    client.close()
    raise TimeoutError("Pipeline timed out")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--resume" in args:
        idx = args.index("--resume")
        exec_id = args[idx + 1]
        results = resume_research(exec_id)
    else:
        topic = " ".join(args) if args else "durable execution for AI agents"
        results = run_research(topic)

    # Print the final report
    if "report" in results:
        print("\n" + "=" * 60)
        print(results["report"].get("content", "No report generated"))
