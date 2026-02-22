# AutoGen #7043 Recovery Demo — Nexum Solution

This demo directly addresses **microsoft/autogen#7043**: *GraphFlow State Persistence Bug*.

## The Problem (AutoGen #7043)

AutoGen `GraphFlow` workflows lose state when interrupted mid-transition between agents. When resumed, the workflow either:
- Terminates immediately saying "execution is complete" (stuck)
- Restarts from the beginning, re-running all completed steps

This is a fundamental limitation: AutoGen stores workflow state in-memory, not durably.

## The Nexum Solution

Nexum commits each node result **atomically** to SQLite/PostgreSQL before moving to the next node. When a worker crashes between steps, a fresh worker picks up exactly where the previous one left off — no human intervention, no lost progress.

```
research → validate → [CRASH] → summarize → report
                                    ↑
                         Fresh worker resumes HERE
                         (not from the beginning)
```

## Pipeline

| Node | Simulates | Depends on |
|---|---|---|
| `research` | LLM agent doing web research | — |
| `validate` | Validator agent checking sources | research |
| `summarize` | Summarizer agent condensing findings | validate |
| `report` | Reporter generating final output | summarize |

## Prerequisites

```bash
# Terminal 1: Nexum server
cd nexum
cargo run --bin nexum-server
```

## Installation

```bash
pip install grpcio protobuf pydantic
# or with pip install nexum-py if published
```

## Run the Demo

```bash
cd nexum/examples/autogen-recovery-demo

# Default: crashes after 'validate', resumes from 'summarize'
python crash_demo.py

# Crash earlier (after research)
python crash_demo.py --crash-after research

# Custom query
python crash_demo.py --query "Impact of Rust on systems programming"
```

## Expected Output

```
════════════════════════════════════════════════════════════
  Step 1: Starting pipeline execution
════════════════════════════════════════════════════════════
  Execution ID: abc123...
  Pipeline:     research → validate → summarize → report

════════════════════════════════════════════════════════════
  Step 2: Worker #1 starts (will crash after 'validate')
════════════════════════════════════════════════════════════
21:15:01 [worker] ▶ [21:15:01] Starting step 'research'...
21:15:01 [worker] ✓ [21:15:02] Completed step 'research'
21:15:02 [worker] ▶ [21:15:02] Starting step 'validate'...
21:15:02 [worker] ✓ [21:15:03] Completed step 'validate'
21:15:03 [worker] 💥 CRASH_AFTER=validate — simulating worker crash (exit 1)

  Worker #1 exited with code: 1
  ✓ Worker #1 crashed as expected (simulating SIGKILL / OOM)

════════════════════════════════════════════════════════════
  Step 3: Checking partial progress in Nexum DB
════════════════════════════════════════════════════════════
  Execution status: RUNNING
  Completed nodes:  ['research', 'validate']

  With AutoGen GraphFlow #7043:
    → Resume → 'execution is complete' (stuck, wrong)

  With Nexum:
    → Resume → picks up from next pending node (correct)

════════════════════════════════════════════════════════════
  Step 4: Worker #2 starts (no crash — fresh, naive worker)
════════════════════════════════════════════════════════════
21:15:06 [worker] ▶ [21:15:06] Starting step 'summarize'...
21:15:06 [worker] ✓ [21:15:07] Completed step 'summarize'
21:15:07 [worker] ▶ [21:15:07] Starting step 'report'...
21:15:07 [worker] ✓ [21:15:08] Completed step 'report'

════════════════════════════════════════════════════════════
  Step 5: Results
════════════════════════════════════════════════════════════
  Final status: COMPLETED
  Resume → done in: 3.2s

  Node timeline:
    ✓ research     (Worker #1)
    ✓ validate     (Worker #1)
    ✓ summarize    (Worker #2) ← resumed here
    ✓ report       (Worker #2)

  ✓ Worker #2 started from 'summarize' — not from the beginning
  ✓ Nodes re-executed by Worker #2: ['summarize', 'report']
```

## How It Works

1. **Atomic commits** — each node's output is stored in SQLite before the next node is scheduled
2. **Stale task reclaim** — if a worker dies holding a task, the server re-queues it after 60s (or immediately when a fresh worker registers)
3. **Stateless workers** — workers carry no state; they just ask "what's next?" and the server answers based on the DB

## Files

| File | Purpose |
|---|---|
| `workflow.py` | Pipeline definition (4 EFFECT nodes) |
| `worker.py` | Executes nodes; supports `CRASH_AFTER` env var |
| `crash_demo.py` | Orchestrates the crash → recovery demo |
| `requirements.txt` | Python dependencies |
