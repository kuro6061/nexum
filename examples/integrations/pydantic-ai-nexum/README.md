# Pydantic AI + Nexum

Durable tool calls for [Pydantic AI](https://ai.pydantic.dev/) agents.

Every tool call (`web_search`, `visit_webpage`) is persisted atomically in
SQLite via Nexum. If the process crashes mid-run and restarts with the same
`SESSION_ID`, already-completed tool calls return from cache instantly — no
re-execution, no duplicate API calls.

## Problem

Pydantic AI tool calls have no built-in persistence. If your agent crashes
after 10 searches, you restart from scratch — all prior tool calls lost.

```
agent.run_sync("research query")
  tool call 1 ✓  # $0.002
  tool call 2 ✓  # $0.002
  tool call 3 ✓  # $0.002
  tool call 4 💥 CRASH — all progress lost, retry from tool call 1
```

## Solution

Each tool call is submitted as a Nexum `EFFECT` workflow with a deterministic
key (`sha256(tool_name + args)`). Nexum guarantees exactly-once execution and
persists results in SQLite.

```
agent.run_sync("research query")
  tool call 1 → Nexum EFFECT → worker executes → result stored in SQLite ✓
  tool call 2 → Nexum EFFECT → worker executes → result stored in SQLite ✓
  tool call 3 💥 CRASH

  # Re-run with same SESSION_ID:
  tool call 1 → [Nexum] cached ⚡  (instant, no re-execution)
  tool call 2 → [Nexum] cached ⚡  (instant, no re-execution)
  tool call 3 → Nexum EFFECT → worker executes → continues from here
```

## Prerequisites

- Python 3.11+
- Nexum server running: `nexum dev` (or `cargo run --bin nexum-server`)
- `GEMINI_API_KEY` or `OPENAI_API_KEY` set

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Terminal 1: Start Nexum server
nexum dev

# Terminal 2: Start worker
python worker.py

# Terminal 3: Run agent
python demo.py "What are the latest developments in durable execution for AI?"

# Re-run same query (tool calls load from cache)
SESSION_ID=my-session python demo.py "What are the latest developments in durable execution for AI?"
```

## Benchmark

Compare plain Pydantic AI vs Pydantic AI + Nexum:

```bash
GEMINI_API_KEY=... python benchmark.py
```

## How It Works

```
Pydantic AI agent
  └─ decides to call web_search("query")
      └─ submit_task.py → NexumClient.start_execution(key=sha256(tool+args))
          └─ worker.py picks up EFFECT node → executes DuckDuckGo search
              └─ result stored in SQLite
                  └─ submit_task.py polls → returns result to agent

On crash + re-run with same SESSION_ID:
  └─ submit_task.py finds existing execution → status=COMPLETED → returns cached ⚡
```

## File Structure

| File | Description |
|------|-------------|
| `demo.py` | Pydantic AI agent with Nexum-backed tools |
| `worker.py` | Nexum worker — executes tool calls |
| `workflow.py` | Nexum workflow definition |
| `submit_task.py` | Helper — submit + poll a tool call |
| `benchmark.py` | Cold vs cached timing comparison |
