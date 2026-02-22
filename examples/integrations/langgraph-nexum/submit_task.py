"""
submit_task.py — Submit a LangGraph tool call as a Nexum workflow.

Uses a deterministic key (sha256 of tool_name + args) so re-runs
with the same session_id return cached results instantly.
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
        with open(path) as f:
            return json.load(f)
    return {}


def _save_session(session_id: str, data: dict) -> None:
    with open(_session_file(session_id), "w") as f:
        json.dump(data, f, indent=2)


def _make_key(tool_name: str, tool_args: dict) -> str:
    payload = tool_name + json.dumps(tool_args, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def submit_tool_call(
    tool_name: str,
    tool_args: dict,
    session_id: str = "default",
    timeout: float = 120,
) -> str:
    """Submit a tool call to Nexum and wait for the result."""
    key = _make_key(tool_name, tool_args)
    session = _load_session(session_id)
    client = NexumClient()

    exec_id = session.get(key)
    if exec_id:
        status = client.get_status(exec_id)
        if status["status"] == "COMPLETED":
            result = status["completedNodes"].get("tool_call", {}).get("result", "")
            print(f"[Nexum] {key} cached ⚡")
            client.close()
            return result
        if status["status"] in ("FAILED", "CANCELLED"):
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
            print(f"[Nexum] waiting ({st})")
            last_log = now
        time.sleep(0.05 if time.time() < fast_until else 0.2)

    client.close()
    raise TimeoutError(f"Nexum execution {exec_id} timed out")
