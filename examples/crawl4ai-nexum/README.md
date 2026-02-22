# Crawl4AI + Nexum Integration

Crash-recoverable parallel web crawling powered by [Crawl4AI](https://github.com/unclecode/crawl4ai) and Nexum.

## Problem

Crawl4AI crawls multiple URLs concurrently, but a crash loses all completed pages. There is no built-in checkpointing or deduplication.

## Solution

Each URL crawl is submitted as a Nexum EFFECT. Nexum persists every completed result in SQLite. On crash or restart, already-crawled URLs return instantly from the database — only the remaining URLs are re-crawled.

## Architecture

```
Input: list of N URLs
  |
  +-- For each URL: submit_crawl_url(url, session_prefix)
  |     session_id = sha256(url)[:16]   (deterministic, URL = cache key)
  |     |
  |     +-> Nexum Server (SQLite) -> Worker (crawl4ai-crawl workflow)
  |                                     |
  |                                     +-> Crawl4AI AsyncWebCrawler
  |                                     |   (or httpx+BS4 fallback)
  |                                     |
  |                                     +-> CrawlOutput {url, markdown, status_code, success}
  |
  +-- Collect results via ThreadPoolExecutor (parallel)
```

## Prerequisites

- Nexum server running on `localhost:50051`
- Python 3.10+

```bash
pip install crawl4ai httpx beautifulsoup4 grpcio protobuf pydantic
crawl4ai-setup  # installs Playwright browsers (optional — httpx fallback available)
```

## Usage

**Terminal 1 — Nexum server:**
```bash
cd nexum && cargo run
```

**Terminal 2 — Worker:**
```bash
cd nexum/examples/crawl4ai-nexum
PYTHONIOENCODING=utf-8 python worker.py
```

**Terminal 3 — Crawl URLs:**
```bash
cd nexum/examples/crawl4ai-nexum
PYTHONIOENCODING=utf-8 python crawler.py https://www.rust-lang.org/ https://go.dev/
```

**Benchmark (all 4 parts):**
```bash
PYTHONIOENCODING=utf-8 python benchmark.py
PYTHONIOENCODING=utf-8 python benchmark.py --crash-after 2
```

## Files

| File | Purpose |
|---|---|
| `worker.py` | Nexum worker: registers `crawl4ai-crawl` workflow, handles `crawl_url` EFFECT |
| `crawler.py` | Client: `submit_crawl_url()` and `crawl_all()` with parallel ThreadPoolExecutor |
| `benchmark.py` | 4-part benchmark: plain vs Nexum fresh vs cached vs crash recovery |

## Key Design Decisions

- **URL-level deduplication**: `sha256(url)[:16]` as session_id means the same URL is never crawled twice within a session.
- **Parallel submission**: `ThreadPoolExecutor(max_workers=5)` submits all URLs concurrently.
- **Adaptive polling**: 50ms for the first 2s (fast results), then 200ms (reduce server load).
- **Graceful fallback**: If Playwright/Crawl4AI is not installed, uses httpx + BeautifulSoup.
