"""
worker.py - Nexum worker that handles 'crawl_url' EFFECT nodes.

Crawls a URL using Crawl4AI (AsyncWebCrawler) and returns markdown content.
Falls back to httpx + BeautifulSoup if Playwright is not available.

Usage:
    PYTHONIOENCODING=utf-8 python worker.py
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from pydantic import BaseModel
from nexum import workflow, NexumClient, Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class CrawlOutput(BaseModel):
    url: str
    markdown: str
    status_code: int
    success: bool


def _crawl_with_crawl4ai(url: str) -> CrawlOutput:
    """Crawl using Crawl4AI AsyncWebCrawler."""
    from crawl4ai import AsyncWebCrawler, CacheMode

    async def do_crawl():
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, cache_mode=CacheMode.BYPASS)
            return result

    result = asyncio.run(do_crawl())
    return CrawlOutput(
        url=url,
        markdown=result.markdown[:50000] if result.markdown else "",
        status_code=result.status_code or 0,
        success=result.success,
    )


def _crawl_with_httpx(url: str) -> CrawlOutput:
    """Fallback: crawl using httpx + BeautifulSoup."""
    import httpx
    from bs4 import BeautifulSoup

    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Trim to 50k chars
        markdown = text[:50000]

        return CrawlOutput(
            url=url,
            markdown=markdown,
            status_code=resp.status_code,
            success=resp.status_code < 400,
        )
    except Exception as e:
        logger.error(f"httpx fallback failed for {url}: {e}")
        return CrawlOutput(url=url, markdown="", status_code=0, success=False)


def handle_crawl(ctx) -> CrawlOutput:
    """Execute a URL crawl and return markdown content."""
    url = ctx.input["url"]
    logger.info(f"Crawling: {url}")

    try:
        result = _crawl_with_crawl4ai(url)
        logger.info(f"Crawl4AI success for {url}: {len(result.markdown)} chars")
        return result
    except Exception as e:
        logger.warning(f"Crawl4AI unavailable ({e}), falling back to httpx+BS4")
        result = _crawl_with_httpx(url)
        logger.info(f"httpx fallback for {url}: {len(result.markdown)} chars")
        return result


# -- Workflow definition -------------------------------------------------------
crawl_workflow = (
    workflow("crawl4ai-crawl")
    .effect("crawl_url", CrawlOutput, handler=handle_crawl, depends_on=[])
    .build()
)


async def main():
    client = NexumClient()

    compat = client.register_workflow(crawl_workflow)
    logger.info(f"Registered workflow: {crawl_workflow.workflow_id} (compatibility: {compat})")

    logger.info("Worker started. Waiting for tasks on localhost:50051 ...")
    w = Worker([crawl_workflow], concurrency=4, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
