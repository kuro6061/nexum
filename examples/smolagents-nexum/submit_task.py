"""
submit_task.py — Submit a smolagents tool call as a Nexum workflow execution.

Uses a deterministic key (sha256 of tool_name + args) so that re-running the
same agent session reuses completed results (crash recovery).

Execution-id mappings are persisted in a local JSON session file so they
survive process restarts.
"""

import hashlib
import json
import os
import time
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from nexum import NexumClient
from workflow import tool_call_workflow


def _session_file(session_id: str) -> str:
    return os.path.join(os.path.dirname(__file__), f".session-{session_id}.json")


def _load_session(session_id: str) -> dict:
    path = _session_file(session_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def _save_session(session_id: str, data: dict) -> None:
    path = _session_file(session_id)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _make_key(tool_name: str, tool_args: dict) -> str:
    """Deterministic key for a tool call (tool_name + canonical args)."""
    payload = tool_name + json.dumps(tool_args, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def submit_tool_call(
    tool_name: str,
    tool_args: dict,
    session_id: str = "default",
    poll_interval: float = 0.5,
    timeout: float = 120,
) -> str:
    """
    Submit a tool call to Nexum and block until the result is available.

    If this exact tool call (same name + args) was already completed in a
    previous run of the same session, the cached result is returned
    immediately — this is the crash-recovery mechanism.

    Returns the tool result as a string.
    """
    key = _make_key(tool_name, tool_args)
    session = _load_session(session_id)

    client = NexumClient()

    # Check if we already have an execution_id for this key
    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("tool_call", {}).get("result", "")
            print(f"[Nexum] {key} already COMPLETED (cached) [done]")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
            # Previous attempt failed; start fresh
            print(f"[Nexum] {key} previous attempt {status['status']}, retrying...")
            exec_id = None

    # Register workflow (idempotent)
    client.register_workflow(tool_call_workflow)

    if exec_id is None:
        # Start a new execution
        exec_id = client.start_execution(
            tool_call_workflow.workflow_id,
            {"tool_name": tool_name, "tool_args": tool_args},
            version_hash=tool_call_workflow.version_hash,
        )
        # Persist mapping immediately so a crash right after submit still recovers
        session[key] = exec_id
        _save_session(session_id, session)
        print(f"[Nexum] Submitted workflow {exec_id[:20]}... for {tool_name}")

    # Poll until complete
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st == "COMPLETED":
            result = status["completedNodes"].get("tool_call", {}).get("result", "")
            print(f"[Nexum] {exec_id[:20]}... COMPLETED [done]")
            client.close()
            return result
        if st in ("FAILED", "CANCELLED"):
            client.close()
            raise RuntimeError(f"Nexum execution {exec_id} {st}")
        print(f"[Nexum] {exec_id[:20]}... {st}...")
        time.sleep(poll_interval)

    client.close()
    raise TimeoutError(f"Nexum execution {exec_id} did not complete within {timeout}s")
