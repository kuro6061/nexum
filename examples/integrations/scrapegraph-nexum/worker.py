"""
worker.py - Nexum worker that handles 'scrape_url' EFFECT nodes.

Uses ScrapeGraphAI SmartScraperGraph with Gemini via OpenAI-compatible endpoint
to extract structured data from web pages.

Usage:
    PYTHONIOENCODING=utf-8 python worker.py
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import sys


from pydantic import BaseModel
from nexum import workflow, NexumClient, Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class ScrapeOutput(BaseModel):
    url: str
    prompt: str
    result: str  # JSON string of extracted data
    success: bool


def _scrape_in_thread(url: str, prompt: str, gemini_key: str) -> dict:
    """
    Run SmartScraperGraph in a fresh thread (no running event loop),
    so scrapegraphai's internal asyncio.run() works without conflict.
    """
    from scrapegraphai.graphs import SmartScraperGraph
    from langchain_openai import ChatOpenAI

    llm_instance = ChatOpenAI(
        model="gemini-2.5-flash",
        openai_api_key=gemini_key,
        openai_api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
        max_tokens=4096,
    )

    graph_config = {
        "llm": {
            "model_instance": llm_instance,
            "model_tokens": 8192,
        },
        "verbose": False,
        "headless": True,
    }

    scraper = SmartScraperGraph(
        prompt=prompt,
        source=url,
        config=graph_config,
    )
    return scraper.run()


def handle_scrape(ctx) -> ScrapeOutput:
    """
    Execute a ScrapeGraphAI SmartScraperGraph extraction.

    Runs the scraper in a ThreadPoolExecutor so that SmartScraperGraph's
    internal asyncio.run() does not conflict with the Nexum worker's
    running event loop.
    """
    url = ctx.input["url"]
    prompt = ctx.input["prompt"]
    logger.info(f"Scraping: {url} (prompt: {prompt[:60]}...)")

    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_scrape_in_thread, url, prompt, gemini_key)
            result = future.result(timeout=90)
        logger.info(f"Scrape success for {url}: {json.dumps(result)[:200]}")
        return ScrapeOutput(
            url=url,
            prompt=prompt,
            result=json.dumps(result),
            success=True,
        )
    except Exception as e:
        raise RuntimeError(f"Scrape failed for {url}: {e}")


# -- Workflow definition -------------------------------------------------------
scrape_workflow = (
    workflow("scrapegraph-scrape")
    .effect("scrape_url", ScrapeOutput, handler=handle_scrape, depends_on=[])
    .build()
)


async def main():
    # Set OpenAI-compat env vars for ScrapeGraphAI
    os.environ["OPENAI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")
    os.environ["OPENAI_BASE_URL"] = "https://generativelanguage.googleapis.com/v1beta/openai"

    client = NexumClient()

    compat = client.register_workflow(scrape_workflow)
    logger.info(f"Registered workflow: {scrape_workflow.workflow_id} (compatibility: {compat})")

    logger.info("Worker started. Waiting for tasks on localhost:50051 ...")
    w = Worker([scrape_workflow], concurrency=4, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
