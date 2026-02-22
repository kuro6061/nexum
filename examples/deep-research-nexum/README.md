# Deep Research + Nexum Integration

Durable, crash-safe deep research using Nexum. Inspired by [dzhng/deep-research](https://github.com/dzhng/deep-research).

## The Problem

Deep research = many parallel LLM calls. Each call costs money and takes time.

Without Nexum:
- 4 sub-queries × ~5s each = 20s+ of LLM work
- Network blip or rate limit at query 3 → all progress lost
- Re-run from scratch = pay for everything again

With Nexum:
- Each sub-query is a durable **EFFECT** node, checkpointed in SQLite
- Crash at query 3 → resume from query 3, queries 1-2 never re-execute
- Same topic re-run → **zero LLM cost** (all from cache)

## Architecture

```
research(topic, n_queries=4)
  │
  ├─ generate_queries(topic)          ← 1 LLM call → [q1, q2, q3, q4]
  │
  ├─ EFFECT: search_and_learn(q1)     ┐
  ├─ EFFECT: search_and_learn(q2)     │  parallel, crash-safe
  ├─ EFFECT: search_and_learn(q3)     │  DuckDuckGo + Gemini
  └─ EFFECT: search_and_learn(q4)     ┘
  │
  ├─ merge_learnings(results)         ← local, free
  │
  └─ write_report(topic, learnings)   ← 1 LLM call → Markdown report
```

Each `search_and_learn` EFFECT:
1. DuckDuckGo search (free, no API key)
2. Gemini extracts 3-5 key learnings
3. Result checkpointed in Nexum SQLite

## LLM Cost Comparison

| Scenario | LLM calls | Cost |
|---|---|---|
| Plain sequential (4 queries) | 4 | $$ |
| Nexum fresh run (4 queries) | 4 | $$ |
| Nexum re-run (same topic+session) | **0** | **$0** |
| Crash at query 2, resume | **2** | **50% saved** |
| Rate limit retry (failed query) | **1** | **75% saved** |

## Setup

```bash
pip install nexum ddgs openai
export GEMINI_API_KEY="your-key"
```

## Usage

### 1. Start the Nexum server

```bash
nexum dev
```

### 2. Start the worker

```bash
PYTHONIOENCODING=utf-8 python worker.py
```

### 3. Run a research task

```bash
PYTHONIOENCODING=utf-8 python researcher.py "Impact of Rust programming language in 2025"
```

### 4. Run the benchmark

```bash
PYTHONIOENCODING=utf-8 python benchmark.py
PYTHONIOENCODING=utf-8 python benchmark.py --crash-after 2 --queries 4
```

## Files

| File | Purpose |
|---|---|
| `worker.py` | Nexum worker: `search_and_learn` EFFECT (DuckDuckGo + Gemini) |
| `researcher.py` | Client: generate queries, submit parallel EFFECTs, write report |
| `benchmark.py` | 4-part benchmark: plain vs Nexum vs cached vs crash recovery |

## How It Differs from gpt-researcher Demo

| | gpt-researcher-nexum | deep-research-nexum |
|---|---|---|
| Granularity | Whole research = 1 EFFECT | Each sub-query = 1 EFFECT |
| Crash recovery | Full restart | Per-query restart |
| Parallelism | Sequential | Parallel (max_workers=4) |
| Rate limit 429 | Full retry | Only failed query retries |
| Dependencies | gpt-researcher | ddgs + openai (lightweight) |
