# LangGraph + Nexum

Exactly-once tool execution for [LangGraph](https://github.com/langchain-ai/langgraph) agents.

## LangGraph Checkpointing vs Nexum Tool Cache

LangGraph already has checkpointing (`MemorySaver`, `SqliteSaver`, `PostgresSaver`).
These two features are **complementary, not competing**:

| Feature | LangGraph Checkpointing | Nexum Tool Cache |
|---------|------------------------|-----------------|
| What's saved | Graph state (messages, node position) | Individual tool call results |
| Re-run behavior | Replays from last checkpoint | Tool calls return cached results ⚡ |
| Exactly-once tools | No — tools re-execute on replay | **Yes** |
| Cross-session cache | No (per-thread) | Yes (deterministic key) |

### The Gap

When LangGraph resumes from a checkpoint, it re-executes any tool calls
that happened after the checkpoint. For expensive tools (LLM calls, web
searches, API requests), this means wasted money and time.

```
# LangGraph with MemorySaver
graph.invoke(query, config={"thread_id": "1"})
  web_search("topic A") ✓  → saved in checkpoint
  web_search("topic B") ✓  → saved in checkpoint
  visit_webpage("url")  💥 CRASH

# Resume:
graph.invoke(query, config={"thread_id": "1"})
  web_search("topic A") 🔄  re-executed (even though we have the result!)
  web_search("topic B") 🔄  re-executed
  visit_webpage("url")  → continues here
```

### With Nexum

```
# LangGraph + Nexum
graph.invoke(query)
  web_search("topic A") → Nexum EFFECT → stored in SQLite ✓
  web_search("topic B") → Nexum EFFECT → stored in SQLite ✓
  visit_webpage("url")  💥 CRASH

# Re-run with same SESSION_ID:
  web_search("topic A") → [Nexum] cached ⚡  (0ms, free)
  web_search("topic B") → [Nexum] cached ⚡  (0ms, free)
  visit_webpage("url")  → Nexum EFFECT → executes here
```

## Prerequisites

- Python 3.11+
- Nexum server: `nexum dev`
- `GEMINI_API_KEY` or `OPENAI_API_KEY`

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
GEMINI_API_KEY=... python demo.py "What is LangGraph used for?"

# Re-run same session — tool calls load from cache
SESSION_ID=my-session GEMINI_API_KEY=... python demo.py "What is LangGraph used for?"
```

## Benchmark

```bash
GEMINI_API_KEY=... python benchmark.py
```

## File Structure

| File | Description |
|------|-------------|
| `demo.py` | `create_react_agent` with Nexum-backed `@tool` functions |
| `worker.py` | Nexum worker — executes tool calls |
| `workflow.py` | Nexum workflow definition |
| `submit_task.py` | Submit + poll helper |
| `benchmark.py` | Plain vs Nexum + checkpointing vs tool cache comparison |
