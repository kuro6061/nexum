# OpenAI Agents SDK + Nexum

Durable tool calls for [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) agents.

Every `@function_tool` call is persisted atomically in SQLite via Nexum.
If the process crashes mid-run and restarts with the same `SESSION_ID`,
already-completed tool calls return from cache instantly.

## Problem

OpenAI Agents SDK `@function_tool` calls have no built-in persistence.
A crash mid-run means all prior tool calls are lost and must be re-executed.

```
Runner.run(agent, "research query")
  web_search("topic A") ✓
  web_search("topic B") ✓
  visit_webpage("url")  💥 CRASH — restart from web_search("topic A")
```

## Solution

Each `@function_tool` call is submitted as a Nexum `EFFECT` workflow.
Nexum guarantees exactly-once execution and persists results in SQLite.

```
Runner.run(agent, "research query")
  web_search("topic A") → Nexum EFFECT → stored ✓
  web_search("topic B") → Nexum EFFECT → stored ✓
  visit_webpage("url")  💥 CRASH

  # Re-run with same SESSION_ID:
  web_search("topic A") → [Nexum] cached ⚡
  web_search("topic B") → [Nexum] cached ⚡
  visit_webpage("url")  → Nexum EFFECT → continues here
```

## Prerequisites

- Python 3.11+
- Nexum server running: `nexum dev`
- `OPENAI_API_KEY` (or `GEMINI_API_KEY` for Gemini via litellm)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Terminal 1
nexum dev

# Terminal 2
python worker.py

# Terminal 3
OPENAI_API_KEY=... python demo.py "Explain durable execution for AI agents"

# Re-run (tool calls load from cache)
SESSION_ID=my-session OPENAI_API_KEY=... python demo.py "Explain durable execution for AI agents"
```

## Benchmark

```bash
OPENAI_API_KEY=... python benchmark.py
```

## File Structure

| File | Description |
|------|-------------|
| `demo.py` | OpenAI Agents agent with Nexum-backed `@function_tool`s |
| `worker.py` | Nexum worker — executes tool calls |
| `workflow.py` | Nexum workflow definition |
| `submit_task.py` | Submit + poll helper |
| `benchmark.py` | Cold vs cached timing comparison |
