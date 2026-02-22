"""
submit_task.py — Submit a Pydantic AI tool call as a Nexum workflow execution.

Uses a deterministic key (sha256 of tool_name + args) so that re-running the
same agent session reuses completed results (crash recovery).

Execution-id mappings are persisted in a local JSON session file so they
survive process restarts.
"""

import hashlib
import json
import os
import time

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

    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("tool_call", {}).get("result", "")
            print(f"[Nexum] {key} already COMPLETED (cached) ⚡")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
            print(f"[Nexum] {key} previous attempt {status['status']}, retrying...")
            exec_id = None

    client.register_workflow(tool_call_workflow)

    if exec_id is None:
        exec_id = client.start_execution(
            tool_call_workflow.workflow_id,
            {"tool_name": tool_name, "tool_args": tool_args},
            version_hash=tool_call_workflow.version_hash,
        )
        session[key] = exec_id
        _save_session(session_id, session)
        print(f"[Nexum] Submitted {exec_id[:16]}... ({tool_name})")

    deadline = time.time() + timeout
    fast_until = time.time() + 2.0
    last_log = 0.0

    while time.time() < deadline:
        status = client.get_status(exec_id)
        st = status["status"]
        if st == "COMPLETED":
            result = status["completedNodes"].get("tool_call", {}).get("result", "")
            print(f"[Nexum] {exec_id[:16]}... done ✓")
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
