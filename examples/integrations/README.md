# Nexum Integration Examples

Python examples showing how to add Nexum's durable execution to popular AI/ML frameworks.

## Prerequisites

- Nexum server running: `nexum dev` (or `cargo run --bin nexum-server`)
- Python 3.11+

## Running any integration

```bash
# Terminal 1: Start Nexum server
nexum dev

# Terminal 2: Install and run
cd examples/integrations/<name>
pip install -r requirements.txt
python worker.py &   # start worker
python demo.py "your query"
```

## Integrations

| Integration | Framework | Description |
|-------------|-----------|-------------|
| `autogen-nexum/` | Microsoft AutoGen v0.4 | Durable tool calls for AutoGen agents — crash recovery + cached re-runs |
| `pydantic-ai-nexum/` | Pydantic AI | Durable `@agent.tool_plain` calls — SQLite-backed persistence for any model |
| `openai-agents-nexum/` | OpenAI Agents SDK | Durable `@function_tool` calls — crash recovery for OpenAI/Gemini agents |
| `browser-use-nexum/` | browser-use | Durable browser sessions — multi-step research pipeline with crash recovery |
| `smolagents-nexum/` | HuggingFace smolagents | Tool execution persistence for `ToolCallingAgent` |
| `crawl4ai-nexum/` | crawl4ai | Resilient web crawling with exactly-once page fetches |
| `deep-research-nexum/` | custom | Multi-step research pipeline with crash recovery |
| `gpt-researcher-nexum/` | GPT-Researcher | Nexum-backed retriever for durable research workflows |
| `ragas-nexum/` | RAGAS | Durable RAG evaluation — resume interrupted eval runs |
| `scrapegraph-nexum/` | ScrapeGraph | Persistent scraping pipelines |

## Common pattern

Every integration follows the same structure:

```
<framework>-nexum/
  demo.py          # main entrypoint — wires framework to Nexum tool calls
  worker.py        # Nexum worker — executes EFFECT nodes
  workflow.py      # Nexum workflow definition
  submit_task.py   # helper — submit + poll a single tool call
  benchmark.py     # cold vs cached timing comparison
  requirements.txt # includes -e ../../../packages/sdk-python
  README.md        # integration-specific setup
```

## How it works

Each framework tool call is submitted as a Nexum `EFFECT` workflow:

```
Framework agent
  └─ decides to call a tool
      └─ submit_task.py → gRPC StartExecution(workflow_key=sha256(tool+args))
          └─ worker.py picks up task → executes tool → stores result in SQLite
              └─ submit_task.py polls GetExecution → returns result to agent

On crash + re-run:
  └─ submit_task.py finds existing execution (same key) → returns cached result ⚡
```

## Crash recovery demo

Each integration includes a crash recovery scenario:

```bash
# Run with simulated crash
python demo.py --crash-after-step 1 "your query"

# Re-run — completed steps load from Nexum cache
python demo.py "your query"
# [Nexum] step already COMPLETED (cached) ⚡
```

## Benchmark

Compare cold run vs cached re-run:

```bash
python benchmark.py
```
