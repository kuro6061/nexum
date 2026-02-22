"""
scraper.py - Submit (url, prompt) pairs as Nexum workflow executions.

Provides:
  submit_scrape(url, prompt, session_prefix) -> dict   (single URL)
  scrape_all(tasks, session_prefix, max_workers)        (parallel batch)

Each (url, prompt) pair gets a deterministic session_id = sha256(url + prompt)[:16]
so re-running with the same inputs reuses the cached result (crash recovery).

Usage:
    PYTHONIOENCODING=utf-8 python scraper.py https://example.com "Extract the page title"
"""

import concurrent.futures
import hashlib
import json
import os
import sys
import time


from pydantic import BaseModel
from nexum import workflow, NexumClient


# -- Workflow definition (must match worker.py) --------------------------------

class ScrapeOutput(BaseModel):
    url: str
    prompt: str
    result: str  # JSON string of extracted data
    success: bool


def _placeholder_handler(ctx):
    raise RuntimeError("scrape_url handler should be executed by worker.py, not inline")


scrape_workflow = (
    workflow("scrapegraph-scrape")
    .effect("scrape_url", ScrapeOutput, handler=_placeholder_handler, depends_on=[])
    .build()
)


# -- Session persistence -------------------------------------------------------

def _session_file(session_prefix: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f".session-{session_prefix}.json")


def _load_session(session_prefix: str) -> dict:
    path = _session_file(session_prefix)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_session(session_prefix: str, data: dict) -> None:
    path = _session_file(session_prefix)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# -- Core functions ------------------------------------------------------------

def _make_key(url: str, prompt: str) -> str:
    """Deterministic key for a (url, prompt) pair."""
    return hashlib.sha256((url + prompt).encode()).hexdigest()[:16]


def submit_scrape(
    url: str,
    prompt: str,
    session_prefix: str = "default",
    timeout: float = 120,
) -> dict:
    """
    Submit a single scrape task to Nexum and block until the result is available.

    If this (url, prompt) was already completed in a previous run of the same
    session, the cached result is returned immediately (crash recovery).

    Returns a ScrapeOutput dict.
    """
    key = _make_key(url, prompt)
    session = _load_session(session_prefix)

    client = NexumClient()

    # Check if we already have an execution_id for this key
    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("scrape_url", {})
            print(f"[Nexum] {key} already COMPLETED (cached) [done]")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
            print(f"[Nexum] {key} previous attempt {status['status']}, retrying...")
            exec_id = None

    # Register workflow (idempotent)
    client.register_workflow(scrape_workflow)

    if exec_id is None:
        exec_id = client.start_execution(
            scrape_workflow.workflow_id,
            {"url": url, "prompt": prompt},
            version_hash=scrape_workflow.version_hash,
        )
        session[key] = exec_id
        _save_session(session_prefix, session)
        print(f"[Nexum] Submitted {exec_id[:16]}... ({url})")

    # Adaptive polling: tight (50ms) for first 2s, then relaxed (200ms)
    deadline = time.time() + timeout
    fast_until = time.time() + 2.0
    last_log = 0.0

    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st == "COMPLETED":
            result = status["completedNodes"].get("scrape_url", {})
            print(f"[Nexum] {exec_id[:16]}... done ({url})")
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
    raise TimeoutError(f"Nexum execution {exec_id} did not complete within {timeout}s")


def scrape_all(
    tasks: list,
    session_prefix: str = "default",
    max_workers: int = 3,
) -> dict:
    """
    Submit all (url, prompt) pairs in parallel and collect results.

    Args:
        tasks: list of (url, prompt) tuples
        session_prefix: session key for crash recovery
        max_workers: max parallel submissions (default 3, LLM calls are expensive)

    Returns:
        {url: result_dict}
    """
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(submit_scrape, url, prompt, session_prefix): url
            for url, prompt in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as e:
                results[url] = {"error": str(e)}
    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scraper.py <url> <prompt>")
        sys.exit(1)

    url = sys.argv[1]
    prompt = sys.argv[2]
    result = submit_scrape(url, prompt, session_prefix="cli")
    print(json.dumps(result, indent=2))
