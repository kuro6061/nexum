# browser-use + Nexum

Durable multi-step browser research pipeline using [browser-use](https://github.com/browser-use/browser-use) and Nexum.

Unlike other integrations where individual tool calls are wrapped, here each
**entire browser-use `Agent.run()`** is a Nexum EFFECT node. If the browser
crashes or the process is killed, the pipeline resumes from the last completed
browser session — no re-browsing, no duplicate LLM costs.

## Pipeline

```
topic input
  │
  ▼ EFFECT: research     — browser-use browses top sources
  │
  ▼ COMPUTE: summarize   — local text processing (no browser)
  │
  ▼ EFFECT: follow_up    — browser-use researches follow-up questions
  │
  ▼ COMPUTE: report      — generate structured report
```

## Problem

Browser automation is expensive and crash-prone:
- Browser crashes mid-research → restart all browsing from scratch
- Each `Agent.run()` costs LLM tokens + time (30s–3min per task)
- Cloud spot instances, OOM kills, network drops are common

```
Pipeline step 1: research ✓      (2 min, $0.05)
Pipeline step 2: summarize ✓     (1 sec, free)
Pipeline step 3: follow_up 💥    CRASH — restart from step 1
```

## Solution

Each `Agent.run()` is wrapped as a Nexum EFFECT node with exactly-once semantics.

```
Pipeline step 1: research ✓   → stored in SQLite
Pipeline step 2: summarize ✓  → stored in SQLite
Pipeline step 3: follow_up 💥 CRASH

# Restart:
Pipeline step 1: research ✓   → [Nexum] cached ⚡ (instant)
Pipeline step 2: summarize ✓  → [Nexum] cached ⚡ (instant)
Pipeline step 3: follow_up    → browser-use resumes here
```

## Prerequisites

- Python 3.11+
- Chromium: `uvx browser-use install` or `playwright install chromium`
- Nexum server: `nexum dev`
- `GEMINI_API_KEY` or `OPENAI_API_KEY`

## Installation

```bash
pip install -r requirements.txt
uvx browser-use install  # install Chromium
```

## Usage

```bash
# Terminal 1
nexum dev

# Terminal 2
GEMINI_API_KEY=... python worker.py

# Terminal 3
python demo.py "the future of AI agent frameworks"

# Resume after crash (execution ID printed at start)
python demo.py --resume exec-abc123
```

## File Structure

| File | Description |
|------|-------------|
| `demo.py` | Start or resume a research pipeline |
| `worker.py` | Nexum worker — runs browser-use Agent.run() per EFFECT node |
| `workflow.py` | 4-step pipeline workflow definition |
| `requirements.txt` | browser-use, langchain, nexum |

## Why This Is Different

Other Nexum integrations (AutoGen, Pydantic AI, OpenAI Agents) wrap
**individual tool calls** as EFFECT nodes. This integration wraps
**entire browser sessions** — each Agent.run() is atomic and crash-safe.

This is the right abstraction because browser-use's internal tool calls
(click, scroll, type) are not independently useful to checkpoint;
the meaningful unit of work is the complete browsing task.
