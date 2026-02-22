# AutoGen + Nexum: Durable LLM Tool Execution

This example integrates [AutoGen](https://github.com/microsoft/autogen) (v0.4, `autogen-agentchat`) with Nexum to add **crash recovery and retry semantics** to LLM agent tool calls.

## Problem

AutoGen agents run tools in-process with no persistence. If the process dies mid-run, all tool call results are lost and every step must be re-executed from scratch.

## Solution

Each tool call is submitted as a Nexum workflow (single EFFECT node). Results are persisted in the Nexum SQLite DB. On re-run, completed tool calls are retrieved from the DB instead of being re-executed.

```
User query
  ↓
AutoGen AssistantAgent (OpenAI-compatible client → Gemini)
  ↓ decides to call a tool
Nexum submit_task.py → gRPC StartExecution(...)
  ↓
EFFECT node: execute tool (DuckDuckGo / visit_webpage) via worker.py
  ↓
Result stored in Nexum SQLite DB
  ↓
submit_task.py polls GetExecution → returns output to AutoGen agent
```

## Prerequisites

- Nexum server running: `cargo run --bin nexum-server` (from repo root)
- Python 3.10+
- `GEMINI_API_KEY` or another supported LLM API key
- **Windows users**: set `PYTHONIOENCODING=utf-8` to prevent encoding errors

## Installation

```bash
pip install autogen-agentchat autogen-ext[openai] ddgs markdownify grpcio protobuf pydantic
```

## Usage

### Terminal 1: Start Nexum server

```bash
cd nexum
cargo run --bin nexum-server
```

### Terminal 2: Start the Nexum worker

```bash
cd nexum/examples/autogen-nexum
python worker.py
```

### Terminal 3: Run the agent

```bash
cd nexum/examples/autogen-nexum

# Linux/macOS
GEMINI_API_KEY=your-key PYTHONIOENCODING=utf-8 python demo.py "What is the population of Tokyo vs New York?"

# Windows (PowerShell)
$env:GEMINI_API_KEY="your-key"; $env:PYTHONIOENCODING="utf-8"; python demo.py "What is the population of Tokyo vs New York?"
```

## Crash Recovery Demo

The `--crash-after-step N` flag simulates a crash after N tool calls complete:

```bash
# Run 1: crashes after the first tool call
python demo.py --crash-after-step 1 "What is the population of Tokyo vs New York?"

# Run 2: re-run the same query — the first tool call result is loaded from Nexum
# (you'll see "[Nexum] ... already COMPLETED (cached) ✓" in the output)
python demo.py "What is the population of Tokyo vs New York?"
```

Use `--session-id` for explicit session control:

```bash
python demo.py --session-id demo1 --crash-after-step 1 "your question"
python demo.py --session-id demo1 "your question"
```

## Model Override

```bash
# Use Claude instead of Gemini
ANTHROPIC_API_KEY=... NEXUM_MODEL=claude-3-5-sonnet-20241022 python demo.py "..."

# Use GPT-4o
OPENAI_API_KEY=... NEXUM_MODEL=gpt-4o python demo.py "..."
```

## AutoGen #7043 Solution: Crash Recovery for Multi-Agent Pipelines

This example also directly addresses **microsoft/autogen#7043**: *GraphFlow State Persistence Bug*.

AutoGen `GraphFlow` workflows lose state when interrupted mid-transition between agents. When resumed, the workflow either terminates immediately ("execution is complete") or restarts from the beginning.

Nexum commits each node result **atomically** to SQLite/PostgreSQL. When a worker crashes between steps, a fresh worker picks up exactly where the previous one left off.

```
research → validate → [CRASH] → summarize → report
                                    ↑
                         Fresh worker resumes HERE
```

### Run the crash recovery demo

```bash
# Terminal 1: Nexum server
cargo run --bin nexum-server

# Terminal 2: Run the demo (crashes after 'validate', resumes from 'summarize')
cd nexum/examples/autogen-nexum
python crash_demo.py

# Crash earlier (after research)
python crash_demo.py --crash-after research

# Custom query
python crash_demo.py --query "Impact of Rust on systems programming"
```

## Files

| File | Purpose |
|---|---|
| `demo.py` | Main entrypoint — wires AutoGen agent to use Nexum for tool execution |
| `worker.py` | Nexum worker — handles `tool_call` EFFECT nodes (DuckDuckGo / visit_webpage) |
| `submit_task.py` | Helper — submits a workflow with deterministic key, polls until complete |
| `workflow.py` | Workflow definition — single EFFECT node for tool calls |
| `crash_demo.py` | Orchestrates the crash → recovery demo (AutoGen #7043) |
| `pipeline_worker.py` | Worker for the 4-step research pipeline; supports `CRASH_AFTER` env var |
| `pipeline_workflow.py` | Pipeline definition (4 EFFECT nodes: research → validate → summarize → report) |

## How It Works

1. Each tool call gets a deterministic key: `sha256(tool_name + canonical_args)`
2. `submit_task.py` submits the tool call as a Nexum EFFECT workflow and saves the mapping in `.session-<id>.json`
3. The worker picks it up, executes the actual tool, and stores the result in Nexum's SQLite DB
4. On crash and re-run, `submit_task.py` finds the existing execution, checks its status, and returns the cached result if COMPLETED

## Comparison with smolagents-nexum

| | smolagents | AutoGen |
|---|---|---|
| Framework | HuggingFace smolagents | Microsoft AutoGen v0.4 |
| Agent type | `ToolCallingAgent` | `AssistantAgent` |
| Tool registration | `Tool` subclass | `FunctionTool` wrapper |
| Integration point | `tool.forward()` override | plain Python function |
| Multi-agent support | ❌ | ✅ (via AutoGen teams) |
