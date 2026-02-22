"""
researcher.py - Submit deep-research tasks as parallel Nexum EFFECT executions.

Workflow:
  1. generate_queries(topic)     -- 1 LLM call → N sub-queries
  2. search_and_learn × N        -- N parallel Nexum EFFECTs (crash-safe)
  3. merge_learnings(results)    -- local, free
  4. write_report(topic, learnings) -- 1 LLM call → Markdown report

Crash recovery: completed EFFECTs are cached in SQLite.
Re-running the same (topic, session) skips completed queries — zero LLM cost.

Usage:
    PYTHONIOENCODING=utf-8 python researcher.py "Impact of Rust programming language in 2025"
"""

import concurrent.futures
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'packages', 'sdk-python'))

from openai import OpenAI
from nexum import workflow, NexumClient
from pydantic import BaseModel


# --- Shared workflow definition (must match worker.py) ---

class LearnResult(BaseModel):
    query: str
    research_goal: str
    learnings: list[str]
    urls: list[str]


def _placeholder(ctx):
    raise RuntimeError("search_and_learn must be handled by worker.py")


research_workflow = (
    workflow("deep-research")
    .effect("search_and_learn", LearnResult, handler=_placeholder, depends_on=[])
    .build()
)


# --- Session persistence (crash recovery) ---

def _session_file(session_prefix: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f".session-{session_prefix}.json")


def _load_session(session_prefix: str) -> dict:
    path = _session_file(session_prefix)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_session(session_prefix: str, data: dict) -> None:
    with open(_session_file(session_prefix), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _make_key(query: str, goal: str) -> str:
    return hashlib.sha256((query + goal).encode()).hexdigest()[:16]


# --- LLM helpers (direct calls, not via Nexum) ---

def _get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


def generate_queries(topic: str, n: int = 4) -> list[dict]:
    """
    Use Gemini to generate N diverse SERP sub-queries for a research topic.
    Returns list of {query, research_goal}.
    """
    client = _get_client()
    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {
                "role": "system",
                "content": "You are a research planner. Generate diverse, specific search queries to thoroughly research a topic.",
            },
            {
                "role": "user",
                "content": (
                    f"Research topic: {topic}\n\n"
                    f"Generate exactly {n} diverse SERP search queries to research this topic thoroughly. "
                    "For each query, also provide a one-sentence research goal.\n"
                    f"Respond in JSON format:\n"
                    '{"queries": [{"query": "...", "research_goal": "..."}, ...]}'
                ),
            },
        ],
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    queries = data.get("queries", [])[:n]
    print(f"[Research] Generated {len(queries)} sub-queries for: {topic}")
    for i, q in enumerate(queries):
        print(f"  [{i+1}] {q['query']}")
    return queries


def write_report(topic: str, learnings: list[str], urls: list[str]) -> str:
    """Synthesize all learnings into a final Markdown research report."""
    client = _get_client()
    learnings_text = "\n".join(f"- {l}" for l in learnings)
    urls_text = "\n".join(f"- {u}" for u in set(urls))

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {
                "role": "system",
                "content": "You are a research writer. Write comprehensive, well-structured reports.",
            },
            {
                "role": "user",
                "content": (
                    f"Write a comprehensive research report on: {topic}\n\n"
                    f"Based on these key learnings:\n{learnings_text}\n\n"
                    "Format as Markdown with sections. Be detailed and cite specific facts."
                ),
            },
        ],
        max_tokens=2048,
    )
    report = response.choices[0].message.content.strip()
    report += f"\n\n## Sources\n{urls_text}"
    return report


# --- Core: submit one search_and_learn EFFECT ---

def submit_query(
    query: str,
    research_goal: str,
    session_prefix: str = "default",
    timeout: float = 120,
) -> dict:
    """
    Submit a single search_and_learn task to Nexum.
    Returns cached result immediately if already completed.
    """
    key = _make_key(query, research_goal)
    session = _load_session(session_prefix)
    client = NexumClient()

    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("search_and_learn", {})
            print(f"[Nexum] {key} already COMPLETED (cached) [done]")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
            print(f"[Nexum] {key} previous attempt {status['status']}, retrying...")
            exec_id = None

    client.register_workflow(research_workflow)

    if exec_id is None:
        exec_id = client.start_execution(
            research_workflow.workflow_id,
            {"query": query, "research_goal": research_goal},
            version_hash=research_workflow.version_hash,
        )
        session[key] = exec_id
        _save_session(session_prefix, session)
        print(f"[Nexum] Submitted {exec_id[:16]}... ({query[:50]})")

    deadline = time.time() + timeout
    fast_until = time.time() + 2.0
    last_log = 0.0

    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st == "COMPLETED":
            result = status["completedNodes"].get("search_and_learn", {})
            print(f"[Nexum] {exec_id[:16]}... done")
            client.close()
            return result
        if st in ("FAILED", "CANCELLED"):
            client.close()
            raise RuntimeError(f"Nexum execution {exec_id} {st}")

        now = time.time()
        if now - last_log >= 1.0:
            print(f"[Nexum] {exec_id[:16]}... waiting ({st})")
            last_log = now

        time.sleep(0.05 if time.time() < fast_until else 0.2)

    client.close()
    raise TimeoutError(f"Nexum execution {exec_id} timed out")


def research_all(
    queries: list[dict],
    session_prefix: str = "default",
    max_workers: int = 4,
) -> dict:
    """Submit all sub-queries in parallel and collect results."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(submit_query, q["query"], q["research_goal"], session_prefix): q["query"]
            for q in queries
        }
        for future in concurrent.futures.as_completed(futures):
            query = futures[future]
            try:
                results[query] = future.result()
            except Exception as e:
                results[query] = {"error": str(e), "learnings": [], "urls": []}
    return results


# --- High-level research entry point ---

def research(
    topic: str,
    n_queries: int = 4,
    session_prefix: str = "default",
) -> str:
    """
    Full deep-research pipeline with Nexum crash recovery.

    1. Generate N sub-queries (1 LLM call) — saved to session for deterministic re-runs
    2. Run all sub-queries as parallel Nexum EFFECTs (N LLM calls, crash-safe)
    3. Write final report (1 LLM call)

    Re-running with the same session_prefix reuses the same sub-queries,
    so Nexum cache hits are guaranteed for completed queries.
    """
    print(f"\n[Research] Topic: {topic}")
    print(f"[Research] Session: {session_prefix}, Queries: {n_queries}\n")

    # Step 1: Generate sub-queries — load from session if already generated
    session = _load_session(session_prefix)
    if "queries" in session:
        queries = session["queries"]
        print(f"[Research] Loaded {len(queries)} sub-queries from session (cache-safe re-run)")
        for i, q in enumerate(queries):
            print(f"  [{i+1}] {q['query']}")
    else:
        queries = generate_queries(topic, n_queries)
        session["queries"] = queries
        _save_session(session_prefix, session)

    # Step 2: Parallel search + learn (Nexum durable EFFECTs)
    print()
    results = research_all(queries, session_prefix=session_prefix, max_workers=n_queries)

    # Step 3: Merge learnings
    all_learnings = []
    all_urls = []
    for result in results.values():
        all_learnings.extend(result.get("learnings", []))
        all_urls.extend(result.get("urls", []))

    print(f"\n[Research] Collected {len(all_learnings)} learnings from {len(queries)} queries")

    # Step 4: Write final report
    print("[Research] Writing final report...")
    report = write_report(topic, all_learnings, all_urls)
    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python researcher.py <topic> [n_queries] [session_prefix]")
        sys.exit(1)

    topic = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    session = sys.argv[3] if len(sys.argv) > 3 else "cli"

    report = research(topic, n_queries=n, session_prefix=session)
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(report)

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# {topic}\n\n{report}")
    print(f"\nSaved to: {report_path}")
