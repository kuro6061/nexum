# Task: Create examples/autogen-recovery-demo for Nexum

Create a new demo in `examples/autogen-recovery-demo/` that directly addresses the AutoGen GraphFlow State Persistence Bug (microsoft/autogen#7043).

## The Problem (AutoGen #7043)
AutoGen GraphFlow workflows get stuck/unrecoverable when interrupted mid-transition between agents.
When resumed, the workflow terminates immediately saying "execution is complete" even with remaining work.

## What to Build
A Python demo showing:
1. A multi-agent pipeline (researcher → validator → summarizer → reporter) using Nexum's Python SDK
2. Simulate a crash mid-workflow (between validator and summarizer)
3. Show that Nexum resumes EXACTLY from where it left off (not from the beginning, not stuck)
4. Compare contrast: comment showing what AutoGen does vs what Nexum does

## File Structure
```
examples/autogen-recovery-demo/
  README.md         - explains the problem and solution
  workflow.py       - main Nexum workflow (4-step agent pipeline)
  worker.py         - Nexum worker that executes nodes
  crash_demo.py     - runs workflow, crashes mid-way, resumes
  requirements.txt  - nexum-py, httpx or similar
```

## Implementation Details

### workflow.py
Use nexum-py SDK to define:
- EFFECT node "research": Simulates LLM research (sleep 0.5s, return findings)
- EFFECT node "validate": Simulates validation (sleep 0.5s), depends on research  
- EFFECT node "summarize": Simulates summarization (sleep 0.5s), depends on validate
- EFFECT node "report": Final report generation, depends on summarize

### worker.py  
Standard Nexum Python worker that:
- Handles all 4 node types
- Each handler prints which step it's running with timestamp
- Has CRASH_AFTER env var: if set to "validate", worker exits(1) after completing validate node

### crash_demo.py
Script that:
1. Starts Nexum server (subprocess, port 15152)
2. Registers and starts the workflow
3. Starts worker with CRASH_AFTER=validate → worker crashes after validate completes
4. Waits 2 seconds
5. Starts fresh worker (no CRASH_AFTER) → should resume from summarize, NOT restart
6. Polls until COMPLETED
7. Prints timeline showing which steps ran in which worker instance

### README.md
- Explain the AutoGen #7043 bug
- Explain how Nexum solves it (atomic node commits, crash recovery, stale task reclaim)
- Show the output of running crash_demo.py
- Link to the AutoGen issue

## Important Notes
- Use nexum-py from workspace (packages/sdk-python) or pip install nexum-py
- Server binary is at: crates/nexum-server/ (cargo build)
- Look at examples/smolagents-nexum/ for reference on how Python examples are structured
- Each node result is committed atomically - a crash between nodes loses nothing
- The stale task reclaim (60s timeout) will automatically re-queue any in-progress task if worker dies

Keep it concise and runnable. The goal is a compelling demo that can be linked in the AutoGen GitHub issue.
