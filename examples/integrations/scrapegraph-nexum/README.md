# ScrapeGraphAI + Nexum Integration

Crash recovery and LLM cost savings for structured web scraping.

[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai) combines HTTP fetching with LLM extraction to produce structured JSON from web pages. Each scrape = HTTP fetch + LLM call, which means **each scrape costs money**.

Without Nexum, scraping 20 URLs crashes midway = all progress lost + wasted LLM spend.
With Nexum, each URL's extracted data is checkpointed in SQLite. Re-runs skip completed URLs entirely — **zero LLM cost on cache hits**.

## Key Value Proposition: LLM Cost Savings

| Scenario | LLM Calls | Cost |
|---|---|---|
| Plain ScrapeGraphAI (20 URLs) | 20 | $$ |
| Nexum fresh run (20 URLs) | 20 | $$ |
| Nexum re-run (same URLs, same prompt) | **0** | **$0** |
| Crash at URL 15, resume | **5** | 75% saved |

Every cached result = one fewer LLM API call = real money saved.

## Architecture

```
Input: [(url1, prompt), (url2, prompt), ...]
  |
  +-- sha256(url + prompt)[:16] -> deterministic session_id
  |
  +-- Submit all as parallel Nexum EFFECTs (max_workers=3)
  |
  +-- Each EFFECT: SmartScraperGraph(url, prompt) -> structured JSON
  |
  +-- Results cached in SQLite -> re-runs are free
```

## Setup

```bash
pip install scrapegraphai nexum
export GEMINI_API_KEY="your-gemini-api-key"
```

## Usage

### 1. Start the Nexum server

```bash
nexum-server
```

### 2. Start the worker

```bash
python worker.py
```

### 3. Run the benchmark

```bash
python benchmark.py
python benchmark.py --crash-after 2
```

### 4. Use the scraper directly

```python
from scraper import submit_scrape, scrape_all

# Single URL
result = submit_scrape(
    "https://www.python.org/",
    "Extract: language name and latest version",
    session_prefix="my-session",
)

# Parallel batch
tasks = [
    ("https://www.rust-lang.org/", "Extract language name and use cases"),
    ("https://go.dev/", "Extract language name and use cases"),
]
results = scrape_all(tasks, session_prefix="batch-1", max_workers=3)
```

## Files

| File | Purpose |
|---|---|
| `worker.py` | Nexum worker: `scrape_url` EFFECT via SmartScraperGraph |
| `scraper.py` | Client: submit scrape tasks with crash recovery + caching |
| `benchmark.py` | 4-part benchmark: plain vs Nexum vs cached vs crash recovery |

## How It Differs from Crawl4AI Demo

| | Crawl4AI | ScrapeGraphAI |
|---|---|---|
| Output | Raw markdown | Structured JSON (LLM-extracted) |
| Per-URL cost | HTTP fetch only | HTTP fetch + LLM call |
| Cache benefit | Save HTTP roundtrip | **Save LLM API cost ($$)** |
| Nexum value | Retry network errors | Retry LLM + network, save money |

## Benchmark Parts

- **Part A**: Plain SmartScraperGraph sequential — baseline, no caching
- **Part B**: Nexum fresh parallel — same LLM calls, faster via parallelism
- **Part C**: Nexum cached — same session re-run, all from SQLite, **zero LLM cost**
- **Part D**: Crash simulation — crash after N URLs, resume skips completed ones
