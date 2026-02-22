"""
crawler.py - Submit URLs as Nexum workflow executions and collect results.

Provides:
  submit_crawl_url(url, session_prefix) -> dict   (single URL)
  crawl_all(urls, session_prefix, max_workers)     (parallel batch)

Each URL gets a deterministic session_id = sha256(url)[:16] so re-running
with the same URL reuses the cached crawl result (crash recovery).

Usage:
    PYTHONIOENCODING=utf-8 python crawler.py https://example.com
"""

import concurrent.futures
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from pydantic import BaseModel
from nexum import workflow, NexumClient


# -- Workflow definition (must match worker.py) --------------------------------

class CrawlOutput(BaseModel):
    url: str
    markdown: str
    status_code: int
    success: bool


def _placeholder_handler(ctx):
    raise RuntimeError("crawl_url handler should be executed by worker.py, not inline")


crawl_workflow = (
    workflow("crawl4ai-crawl")
    .effect("crawl_url", CrawlOutput, handler=_placeholder_handler, depends_on=[])
    .build()
)


# -- Session persistence -------------------------------------------------------

def _session_file(session_prefix: str) -> str:
    return os.path.join(os.path.dirname(__file__), f".session-{session_prefix}.json")


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

def _make_key(url: str) -> str:
    """Deterministic key for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def submit_crawl_url(
    url: str,
    session_prefix: str = "default",
    timeout: float = 120,
) -> dict:
    """
    Submit a single URL crawl to Nexum and block until the result is available.

    If this URL was already completed in a previous run of the same session,
    the cached result is returned immediately (crash recovery).

    Returns a CrawlOutput dict.
    """
    key = _make_key(url)
    session = _load_session(session_prefix)

    client = NexumClient()

    # Check if we already have an execution_id for this URL
    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("crawl_url", {})
            print(f"[Nexum] {key} already COMPLETED (cached) [done]")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
            print(f"[Nexum] {key} previous attempt {status['status']}, retrying...")
            exec_id = None

    # Register workflow (idempotent)
    client.register_workflow(crawl_workflow)

    if exec_id is None:
        exec_id = client.start_execution(
            crawl_workflow.workflow_id,
            {"url": url},
            version_hash=crawl_workflow.version_hash,
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
            result = status["completedNodes"].get("crawl_url", {})
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


def crawl_all(
    urls: list,
    session_prefix: str = "default",
    max_workers: int = 5,
) -> dict:
    """Submit all URLs in parallel and collect results."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(submit_crawl_url, url, session_prefix): url
            for url in urls
        }
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as e:
                results[url] = {"error": str(e)}
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python crawler.py <url> [url2 ...]")
        sys.exit(1)

    urls = sys.argv[1:]
    results = crawl_all(urls, session_prefix="cli")
    for url, result in results.items():
        md_len = len(result.get("markdown", "")) if isinstance(result, dict) else 0
        ok = result.get("success", False) if isinstance(result, dict) else False
        print(f"  {url}: {'OK' if ok else 'FAIL'} ({md_len} chars)")
