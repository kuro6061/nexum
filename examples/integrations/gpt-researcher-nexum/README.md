# gpt-researcher + Nexum: Crash-Recoverable Web Research

This example integrates [gpt-researcher](https://github.com/assafelovic/gpt-researcher) with Nexum to add **crash recovery** to multi-step web research workflows.

## Problem

gpt-researcher performs deep research by planning sub-queries, fetching search results for each, scraping web pages, and writing a comprehensive report. This process takes 2-5 minutes on complex queries. If the process dies mid-way (OOM, kill, timeout), all fetched sub-query results are lost and must be re-fetched from scratch.

## Solution

Replace gpt-researcher's default DuckDuckGo retriever with `NexumDuckduckgo`, which routes every search through a Nexum workflow. Each sub-query result is persisted in the Nexum SQLite DB. On re-run, completed sub-queries are retrieved from the DB instead of re-executed.

```
User query
  │
  ▼
GPTResearcher (LLM plans sub-queries)
  │  calls NexumDuckduckgo.search() for each sub-query
  ▼
nexum_retriever.py → submit_tool_call() → Nexum gRPC
  │
  ▼  (smolagents-nexum Worker — reused)
EFFECT node: DuckDuckGoSearchTool(**args)
  │
  ▼
Result stored in Nexum SQLite DB
  │
  ▼
submit_tool_call() polls → returns results to GPTResearcher
```

**Key insight**: This integration reuses the existing `smolagents-nexum` worker and workflow. No new worker is needed — the same `web_search` EFFECT handles both smolagents and gpt-researcher requests.

## Prerequisites

- Nexum server running: `cargo run --bin nexum-server` (from repo root)
- Python 3.10+
- `GEMINI_API_KEY` (or any OpenAI-compatible LLM API key)
- **Windows users**: set `PYTHONIOENCODING=utf-8`

## Installation

```bash
pip install gpt-researcher duckduckgo-search grpcio protobuf pydantic
```

## Usage

### Terminal 1: Start Nexum server

```bash
cd nexum && cargo run --bin nexum-server
```

### Terminal 2: Start the worker (reuse smolagents-nexum worker)

```bash
cd nexum/examples/smolagents-nexum
python worker.py
```

### Terminal 3: Run gpt-researcher

```bash
cd nexum/examples/gpt-researcher-nexum

# Linux/macOS
GEMINI_API_KEY=your-key PYTHONIOENCODING=utf-8 python demo.py "What are the main differences between Rust and Go for systems programming?"

# Windows (PowerShell)
$env:GEMINI_API_KEY="your-key"; $env:PYTHONIOENCODING="utf-8"; python demo.py "What are the main differences between Rust and Go for systems programming?"
```

## Crash Recovery

Each sub-query search gets a deterministic session id based on the main query + sub-query hash. If the process crashes mid-research:

1. First run fetches sub-queries 1..N, crashes at sub-query K
2. Sub-queries 1..K-1 are already persisted in Nexum
3. Re-run the same query: sub-queries 1..K-1 load from cache, only K..N are fetched fresh

## Benchmark

The benchmark compares the retriever layer (no full GPTResearcher) across three modes:

```bash
PYTHONIOENCODING=utf-8 python benchmark.py
```

- **A. Direct**: Raw DuckDuckGo searches (baseline)
- **B. Nexum fresh**: Same searches routed through Nexum (measures gRPC overhead)
- **C. Nexum cached**: Same searches again (all cached — crash recovery scenario)

## Files

| File | Purpose |
|---|---|
| `nexum_retriever.py` | `NexumDuckduckgo` class — drop-in retriever for gpt-researcher |
| `demo.py` | Main entrypoint — runs GPTResearcher with Nexum-backed retriever |
| `benchmark.py` | Controlled overhead measurement (direct vs Nexum vs cached) |

## How It Works

`NexumDuckduckgo` implements the gpt-researcher retriever interface:

```python
class NexumDuckduckgo:
    def __init__(self, query: str, query_domains=None): ...
    def search(self, max_results: int = 5) -> list[dict]: ...
```

In `search()`, it calls `submit_tool_call("web_search", {...})` from the smolagents-nexum integration. The result is a JSON string of search results, which is parsed back to `list[dict]` for gpt-researcher.
