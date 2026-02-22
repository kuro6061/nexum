"""
pipeline_worker.py  ENexum worker for the AutoGen #7043 recovery demo.

Handles the 4-step research pipeline (research ↁEvalidate ↁEsummarize ↁEreport).

Environment variables:
    CRASH_AFTER   EIf set (e.g. "validate"), the worker exits(1) immediately
                   after that node completes, simulating a crash.

Usage:
    # Normal run:
    python pipeline_worker.py

    # Crash after "validate" node:
    CRASH_AFTER=validate python pipeline_worker.py
"""

import asyncio
import logging
import os
import sys
import time


from pydantic import BaseModel
from nexum import workflow, NexumClient, Worker

CRASH_AFTER = os.environ.get("CRASH_AFTER", "").strip().lower()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(message)s",
)
logger = logging.getLogger(__name__)


class StepOutput(BaseModel):
    step: str
    result: str


def _step(name: str, work_fn):
    """Factory: creates a handler for a pipeline step."""
    def handler(ctx):
        ts = time.strftime("%H:%M:%S")
        logger.info(f"▶ [{ts}] Starting step '{name}'...")
        result = work_fn(ctx)
        ts2 = time.strftime("%H:%M:%S")
        logger.info(f"✁E[{ts2}] Completed step '{name}'")

        if CRASH_AFTER == name:
            logger.warning(f"💥 CRASH_AFTER={name}  Esimulating worker crash (exit 1)")
            # Give the server a moment to commit the result
            time.sleep(0.2)
            os._exit(1)  # Hard exit  Esimulates OOM / SIGKILL

        return StepOutput(step=name, result=result)
    return handler


def research_handler(ctx):
    # Simulate: LLM agent doing web research
    query = ctx.input.get("query", "unknown topic")
    time.sleep(0.5)
    findings = (
        f"Research findings on '{query}': "
        "Found 5 relevant sources. Key insight: this topic has significant "
        "implications for distributed systems. Primary evidence from arXiv 2024."
    )
    return _step("research", lambda _: findings)(ctx)


def validate_handler(ctx):
    # Simulate: validator agent checking the research
    research = ctx.get("research")
    time.sleep(0.5)
    validation = (
        f"Validation complete. Research looks solid. "
        f"Sources cross-checked. Confidence: 92%. "
        f"No contradictory evidence found."
    )
    return _step("validate", lambda _: validation)(ctx)


def summarize_handler(ctx):
    # Simulate: summarizer agent condensing findings
    time.sleep(0.5)
    summary = (
        "Executive summary: The topic demonstrates strong potential with "
        "high confidence validation. Recommend proceeding to report phase."
    )
    return _step("summarize", lambda _: summary)(ctx)


def report_handler(ctx):
    # Simulate: reporter agent generating final output
    time.sleep(0.5)
    report = (
        "FINAL REPORT\n"
        "============\n"
        "Based on research, validation, and summarization:\n"
        "• Research phase: completed successfully\n"
        "• Validation: 92% confidence\n"
        "• Recommendation: APPROVED\n"
        "Status: COMPLETE"
    )
    return _step("report", lambda _: report)(ctx)


# We need separate handler functions per node (not using _step factory directly)
# because the factory approach above would double-apply. Let's define cleanly:

def _research(ctx):
    name = "research"
    ts = time.strftime("%H:%M:%S")
    logger.info(f"▶ [{ts}] Starting step '{name}'...")
    query = ctx.input.get("query", "unknown topic")
    time.sleep(0.5)
    result = (
        f"Research findings on '{query}': "
        "Found 5 relevant sources. Key insight: this topic has significant "
        "implications for distributed systems. Primary evidence from arXiv 2024."
    )
    ts2 = time.strftime("%H:%M:%S")
    logger.info(f"✁E[{ts2}] Completed step '{name}'")
    if CRASH_AFTER == name:
        logger.warning(f"💥 CRASH_AFTER={name}  Esimulating worker crash (exit 1)")
        time.sleep(0.2)
        os._exit(1)
    return StepOutput(step=name, result=result)


def _validate(ctx):
    name = "validate"
    ts = time.strftime("%H:%M:%S")
    logger.info(f"▶ [{ts}] Starting step '{name}'...")
    time.sleep(0.5)
    result = (
        "Validation complete. Sources cross-checked. "
        "Confidence: 92%. No contradictory evidence found."
    )
    ts2 = time.strftime("%H:%M:%S")
    logger.info(f"✁E[{ts2}] Completed step '{name}'")
    if CRASH_AFTER == name:
        logger.warning(f"💥 CRASH_AFTER={name}  Esimulating worker crash (exit 1)")
        time.sleep(0.2)
        os._exit(1)
    return StepOutput(step=name, result=result)


def _summarize(ctx):
    name = "summarize"
    ts = time.strftime("%H:%M:%S")
    logger.info(f"▶ [{ts}] Starting step '{name}'...")
    time.sleep(0.5)
    result = (
        "Executive summary: Strong potential with high-confidence validation. "
        "Recommend proceeding to final report."
    )
    ts2 = time.strftime("%H:%M:%S")
    logger.info(f"✁E[{ts2}] Completed step '{name}'")
    if CRASH_AFTER == name:
        logger.warning(f"💥 CRASH_AFTER={name}  Esimulating worker crash (exit 1)")
        time.sleep(0.2)
        os._exit(1)
    return StepOutput(step=name, result=result)


def _report(ctx):
    name = "report"
    ts = time.strftime("%H:%M:%S")
    logger.info(f"▶ [{ts}] Starting step '{name}'...")
    time.sleep(0.5)
    result = (
        "FINAL REPORT\n"
        "============\n"
        "• Research:   ✁Ecompleted\n"
        "• Validation: ✁E92% confidence\n"
        "• Summary:    ✁Eapproved\n"
        "Status: COMPLETE"
    )
    ts2 = time.strftime("%H:%M:%S")
    logger.info(f"✁E[{ts2}] Completed step '{name}'")
    return StepOutput(step=name, result=result)


# Workflow registration
pipeline_workflow = (
    workflow("autogen-research-pipeline")
    .effect("research",  StepOutput, handler=_research,  depends_on=[])
    .effect("validate",  StepOutput, handler=_validate,  depends_on=["research"])
    .effect("summarize", StepOutput, handler=_summarize, depends_on=["validate"])
    .effect("report",    StepOutput, handler=_report,    depends_on=["summarize"])
    .build()
)


async def main():
    client = NexumClient()
    compat = client.register_workflow(pipeline_workflow)
    logger.info(f"Registered pipeline (compatibility: {compat})")

    if CRASH_AFTER:
        logger.info(f"⚠�E�E Will crash after completing node: '{CRASH_AFTER}'")

    logger.info("Worker ready. Waiting for tasks on localhost:50051 ...")
    w = Worker([pipeline_workflow], concurrency=1, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
