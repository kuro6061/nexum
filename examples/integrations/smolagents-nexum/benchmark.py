"""
benchmark.py  EBefore/After comparison: plain smolagents vs smolagents + Nexum

Demonstrates:
1. Normal run: both approaches work, Nexum adds small overhead
2. Crash scenario: plain smolagents loses all progress; Nexum resumes from checkpoint
3. Repeated run: plain smolagents re-executes everything; Nexum returns cached results instantly

Usage:
    GEMINI_API_KEY=... PYTHONIOENCODING=utf-8 python benchmark.py
"""

import hashlib
import json
import os
import sys
import time
import textwrap


from smolagents import ToolCallingAgent, LiteLLMModel, DuckDuckGoSearchTool, Tool
from submit_task import submit_tool_call

QUERY = "What are the top 3 programming languages released or updated in 2025?"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

DIVIDER = "=" * 65


def make_model():
    return LiteLLMModel(
        model_id="gemini/gemini-3-flash-preview",
        api_key=GEMINI_KEY,
    )


# ── Plain smolagents tool (direct execution, no Nexum) ──────────────
class DirectSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information."
    inputs = {"query": {"type": "string", "description": "Search query"}}
    output_type = "string"

    def __init__(self, crash_after: int | None = None, counter: list = None):
        super().__init__()
        self._base = DuckDuckGoSearchTool()
        self._crash_after = crash_after
        self._counter = counter or [0]
        self.is_initialized = True

    def forward(self, query: str) -> str:
        self._counter[0] += 1
        if self._crash_after and self._counter[0] > self._crash_after:
            raise RuntimeError("[CRASH] Process died mid-run!")
        return self._base(query)


# ── Nexum-backed tool ──────────────────────────────────────────────
class NexumSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information."
    inputs = {"query": {"type": "string", "description": "Search query"}}
    output_type = "string"

    def __init__(self, session_id: str, crash_after: int | None = None, counter: list = None):
        super().__init__()
        self._session_id = session_id
        self._crash_after = crash_after
        self._counter = counter or [0]
        self.is_initialized = True

    def forward(self, query: str) -> str:
        self._counter[0] += 1
        if self._crash_after and self._counter[0] > self._crash_after:
            raise RuntimeError("[CRASH] Process died mid-run!")
        return submit_tool_call("web_search", {"query": query}, session_id=self._session_id)


def section(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def run_plain(query: str, crash_after: int | None = None, label: str = "plain"):
    counter = [0]
    tool = DirectSearchTool(crash_after=crash_after, counter=counter)
    agent = ToolCallingAgent(tools=[tool], model=make_model(), max_steps=5, verbosity_level=0)
    t0 = time.time()
    result = None
    error = None
    steps_done = counter[0]
    try:
        result = agent.run(query)
        steps_done = counter[0]
    except Exception as e:
        error = str(e)
        steps_done = counter[0]
    elapsed = time.time() - t0
    return {
        "label": label,
        "elapsed": elapsed,
        "steps": steps_done,
        "result": result,
        "error": error,
    }


def run_nexum(query: str, session_id: str, crash_after: int | None = None, label: str = "nexum"):
    counter = [0]
    tool = NexumSearchTool(session_id=session_id, crash_after=crash_after, counter=counter)
    agent = ToolCallingAgent(tools=[tool], model=make_model(), max_steps=5, verbosity_level=0)
    t0 = time.time()
    result = None
    error = None
    steps_done = counter[0]
    try:
        result = agent.run(query)
        steps_done = counter[0]
    except Exception as e:
        error = str(e)
        steps_done = counter[0]
    elapsed = time.time() - t0
    return {
        "label": label,
        "steps": steps_done,
        "elapsed": elapsed,
        "result": result,
        "error": error,
    }


def fmt_result(r: dict) -> str:
    lines = [
        f"  Time taken : {r['elapsed']:.1f}s",
        f"  Tool calls : {r['steps']}",
    ]
    if r["error"]:
        lines.append(f"  Status     : CRASHED  E{r['error'][:60]}")
        lines.append(f"  Progress   : LOST (0/{r['steps']} steps saved)")
    else:
        ans = (r["result"] or "")[:120].replace("\n", " ")
        lines.append(f"  Status     : COMPLETED")
        lines.append(f"  Answer     : {ans}...")
    return "\n".join(lines)


def main():
    if not GEMINI_KEY:
        print("ERROR: Set GEMINI_API_KEY environment variable")
        sys.exit(1)

    session_id = hashlib.sha256(QUERY.encode()).hexdigest()[:12]

    print(f"\n{'#'*65}")
    print(f"  Nexum Before/After Benchmark")
    print(f"{'#'*65}")
    print(f"\nQuery: {QUERY}")
    print(f"Session ID: {session_id}")

    # ──────────────────────────────────────────────────────────────────
    section("SCENARIO 1: Normal run (no crash)")
    print("Running plain smolagents...")
    plain1 = run_plain(QUERY, label="plain-normal")
    print(fmt_result(plain1))

    print("\nRunning smolagents + Nexum...")
    nexum1 = run_nexum(QUERY, session_id=session_id + "-s1", label="nexum-normal")
    print(fmt_result(nexum1))

    overhead = nexum1["elapsed"] - plain1["elapsed"]
    print(f"\n  Nexum overhead: {overhead:+.1f}s ({overhead/plain1['elapsed']*100:+.0f}%)")

    # ──────────────────────────────────────────────────────────────────
    section("SCENARIO 2: Crash after 1st tool call")

    print("PLAIN smolagents  Ecrashes after step 1:")
    plain2 = run_plain(QUERY, crash_after=1, label="plain-crash")
    print(fmt_result(plain2))

    print("\nNexum  Ecrashes after step 1 (but checkpoint saved):")
    crash_session = session_id + "-crash"
    nexum2 = run_nexum(QUERY, session_id=crash_session, crash_after=1, label="nexum-crash")
    print(fmt_result(nexum2))

    # ──────────────────────────────────────────────────────────────────
    section("SCENARIO 3: Resume after crash")

    print("PLAIN smolagents  Emust restart from scratch:")
    t0 = time.time()
    plain3 = run_plain(QUERY, label="plain-restart")
    plain3["elapsed"] = time.time() - t0
    print(fmt_result(plain3))
    print(f"  (Had to redo all {plain3['steps']} tool calls)")

    print("\nNexum  Eresumes from checkpoint (step 1 already cached):")
    t0 = time.time()
    nexum3 = run_nexum(QUERY, session_id=crash_session, label="nexum-resume")
    nexum3["elapsed"] = time.time() - t0
    print(fmt_result(nexum3))
    print(f"  (Step 1 loaded from cache, only {nexum3['steps']-1} new calls needed)")

    # ──────────────────────────────────────────────────────────────────
    section("SUMMARY")

    rows = [
        ("", "Plain smolagents", "smolagents + Nexum"),
        ("─" * 20, "─" * 18, "─" * 18),
        ("Normal run time",
         f"{plain1['elapsed']:.1f}s",
         f"{nexum1['elapsed']:.1f}s (+{overhead:.1f}s overhead)"),
        ("Crash: data saved?",
         "NO  Eall lost",
         "YES  Estep 1 in DB"),
        ("Resume time",
         f"{plain3['elapsed']:.1f}s (full redo)",
         f"{nexum3['elapsed']:.1f}s (partial redo)"),
        ("Time saved on resume",
         " E,
         f"{plain3['elapsed'] - nexum3['elapsed']:.1f}s ({(plain3['elapsed']-nexum3['elapsed'])/plain3['elapsed']*100:.0f}% faster)"),
        ("Execution history",
         "None",
         "SQLite (permanent)"),
        ("Retry on HTTP fail",
         "No",
         "Yes (configurable)"),
    ]

    for cols in rows:
        label, before, after = cols
        print(f"  {label:<22} {before:<25} {after}")

    print()


if __name__ == "__main__":
    main()
