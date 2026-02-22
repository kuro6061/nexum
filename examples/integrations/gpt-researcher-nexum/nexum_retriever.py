"""
nexum_retriever.py — Custom gpt-researcher retriever backed by Nexum.

NexumDuckduckgo has the same interface as gpt_researcher.retrievers.duckduckgo.Duckduckgo
but routes every search through Nexum, gaining crash recovery and result caching.

Usage:
    import nexum_retriever
    nexum_retriever.MAIN_SESSION = "abc123"  # set before creating GPTResearcher
    researcher = GPTResearcher(query=..., retrievers=[nexum_retriever.NexumDuckduckgo])
"""

import hashlib
import json
import os
import sys

# Make submit_task importable from the sibling smolagents-nexum directory
_smolagents_dir = os.path.join(os.path.dirname(__file__), "..", "smolagents-nexum")
if _smolagents_dir not in sys.path:
    sys.path.insert(0, _smolagents_dir)

from submit_task import submit_tool_call  # noqa: E402

# Module-level session prefix — set this before creating GPTResearcher
MAIN_SESSION = "default"


class NexumDuckduckgo:
    """
    Drop-in replacement for gpt_researcher.retrievers.duckduckgo.Duckduckgo.

    Constructor signature: (query, query_domains=None)
    Method: search(max_results=5) -> list[dict]

    Internally delegates to the Nexum 'smolagents-tool-call' workflow,
    which is handled by the smolagents-nexum worker (web_search EFFECT).
    """

    def __init__(self, query: str, query_domains=None):
        self.query = query
        self.query_domains = query_domains

    def search(self, max_results: int = 5) -> list[dict]:
        """
        Run a DuckDuckGo search via Nexum.

        gpt-researcher calls this synchronously from a thread
        (via asyncio executor), so blocking here is fine.
        """
        # Build a per-sub-query session id for deterministic caching
        sub_hash = hashlib.sha256(self.query.encode()).hexdigest()[:8]
        session_id = f"{MAIN_SESSION}_{sub_hash}"

        result = submit_tool_call(
            "web_search",
            {"query": self.query, "max_results": max_results},
            session_id=session_id,
        )

        # The worker returns json.dumps(list[dict]) via smolagents DuckDuckGoSearchTool.
        # Parse it back to a list.
        try:
            parsed = json.loads(result)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: return as a single-item result
        return [{"body": str(result), "href": "", "title": "search result"}]
