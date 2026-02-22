# smolagents + Nexum: Durable LLM Tool Execution

This example integrates [smolagents](https://github.com/huggingface/smolagents) (HuggingFace) with Nexum to add **crash recovery and retry semantics** to LLM agent tool calls.

## Problem

smolagents runs tools sequentially with no persistence. If the process dies mid-run, all progress is lost and every tool call must be re-executed.

## Solution

Each tool call is submitted as a Nexum workflow (single EFFECT node). Results are persisted in the Nexum SQLite DB. On re-run, completed tool calls are retrieved from the DB instead of re-executed.

```
User query
  │
  ▼
smolagents ToolCallingAgent (LiteLLM → Claude)
  │  decides to call a tool
  ▼
submit_task.py → Nexum gRPC: StartExecution(...)
  │
  ▼  (Nexum Worker)
EFFECT node: execute tool (DuckDuckGoSearchTool / VisitWebpageTool)
  │
  ▼
Result stored in Nexum SQLite DB
  │
  ▼
submit_task.py polls GetExecution → returns output to smolagents agent
```

## Prerequisites

- Nexum server running: `cargo run --bin nexum-server` (from repo root)
- Python 3.10+
- `ANTHROPIC_API_KEY` environment variable set

## Installation

```bash
pip install smolagents litellm anthropic grpcio protobuf pydantic
```

## Usage

### Terminal 1: Start Nexum server

```bash
cd nexum && cargo run --bin nexum-server
```

### Terminal 2: Start the Nexum worker

```bash
cd nexum/examples/smolagents-nexum
python worker.py
```

### Terminal 3: Run the agent

```bash
cd nexum/examples/smolagents-nexum
python demo.py "What is the population of Tokyo and how does it compare to New York?"
```

## Crash Recovery Demo

The `--crash-after-step N` flag simulates a crash after N tool calls complete:

```bash
# Run 1: crashes after the first tool call
python demo.py --crash-after-step 1 "What is the population of Tokyo vs New York?"

# Run 2: re-run the same query — the first tool call result is loaded from Nexum
# (you'll see "[Nexum] ... already COMPLETED (cached)" in the output)
python demo.py "What is the population of Tokyo vs New York?"
```

You can also specify an explicit `--session-id` for more control:

```bash
python demo.py --session-id demo1 --crash-after-step 1 "your question"
python demo.py --session-id demo1 "your question"
```

## Files

| File | Purpose |
|---|---|
| `demo.py` | Main entrypoint — wires smolagents agent to use Nexum for tool execution |
| `worker.py` | Nexum worker — handles `tool_call` EFFECT nodes by running smolagents tools |
| `submit_task.py` | Helper — submits a workflow with deterministic key, polls until complete |
| `workflow.py` | Workflow definition — single EFFECT node for tool calls |

## How Crash Recovery Works

1. Each tool call gets a deterministic key: `sha256(tool_name + canonical_args)`
2. On first execution, `submit_task.py` starts a Nexum workflow and saves the `execution_id` → key mapping in a local session file (`.session-<id>.json`)
3. On re-run, `submit_task.py` finds the existing `execution_id` for the key, checks its status via `GetExecution`, and returns the cached result if COMPLETED
4. The Nexum server persists all results in its SQLite DB, so even if the session file is lost, the data survives in the server
