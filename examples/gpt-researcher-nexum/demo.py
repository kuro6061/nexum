"""
demo.py — Run gpt-researcher with Nexum-backed DuckDuckGo retriever.

All web searches go through Nexum, so completed sub-queries survive crashes.
Re-running the same research question picks up where it left off.

Prerequisites:
    - Nexum server running: cargo run --bin nexum-server
    - smolagents-nexum worker running: python ../smolagents-nexum/worker.py
    - pip install gpt-researcher

Usage:
    GEMINI_API_KEY=your-key PYTHONIOENCODING=utf-8 python demo.py "your research question"
"""

import asyncio
import hashlib
import os
import sys

# ── LLM configuration (Google Gemini via OpenAI-compatible endpoint) ───
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
if _gemini_key:
    os.environ.setdefault("OPENAI_API_KEY", _gemini_key)
    os.environ.setdefault(
        "OPENAI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai",
    )
os.environ.setdefault("FAST_LLM", "gemini-3-flash-preview")
os.environ.setdefault("SMART_LLM", "gemini-3-flash-preview")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("RETRIEVER", "duckduckgo")

import nexum_retriever  # noqa: E402
from gpt_researcher import GPTResearcher  # noqa: E402


async def main():
    if len(sys.argv) < 2:
        print("Usage: python demo.py \"your research question\"")
        sys.exit(1)

    query = sys.argv[1]

    # Set Nexum session context — deterministic from the main query
    nexum_retriever.MAIN_SESSION = hashlib.sha256(query.encode()).hexdigest()[:12]
    print(f"[demo] Query: {query}")
    print(f"[demo] Nexum session prefix: {nexum_retriever.MAIN_SESSION}")
    print()

    researcher = GPTResearcher(
        query=query,
        report_type="research_report",
        retrievers=[nexum_retriever.NexumDuckduckgo],
    )

    await researcher.conduct_research()
    report = await researcher.write_report()

    print("\n" + "=" * 60)
    print("  FINAL REPORT")
    print("=" * 60)
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
