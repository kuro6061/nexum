"""
demo.py — AutoGen AssistantAgent with durable Nexum tool execution.

Each tool call the LLM decides to make is submitted as a Nexum workflow,
giving crash-recovery and retry semantics for free.

Usage:
    python demo.py "What is the population of Tokyo vs New York?"
    python demo.py --crash-after-step 1 "What is the population of Tokyo?"
    python demo.py --session-id my-session "reuse previous results"

Environment variables:
    GEMINI_API_KEY   — Google Gemini API key (default model)
    OPENAI_API_KEY   — OpenAI API key (optional)
    ANTHROPIC_API_KEY — Anthropic API key (optional)
    NEXUM_MODEL      — override model (default: gemini/gemini-2.5-flash-preview-04-17)
"""

import argparse
import asyncio
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from submit_task import submit_tool_call

# ── AutoGen imports ────────────────────────────────────────────────
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.tools import FunctionTool


# ── Global state for crash simulation ─────────────────────────────
_step_counter = [0]
_crash_after_step = [None]
_session_id = ["default"]


# ── Tool implementations (submit via Nexum) ────────────────────────

def web_search(query: str) -> str:
    """Search the web using DuckDuckGo and return the top results as JSON."""
    _step_counter[0] += 1
    if _crash_after_step[0] is not None and _step_counter[0] > _crash_after_step[0]:
        raise RuntimeError(
            f"[CRASH SIMULATION] Process crashing after step {_crash_after_step[0]}! "
            "Re-run to resume from Nexum checkpoint."
        )
    return submit_tool_call("web_search", {"query": query}, session_id=_session_id[0])


def visit_webpage(url: str) -> str:
    """Fetch the content of a webpage and return it as markdown text."""
    _step_counter[0] += 1
    if _crash_after_step[0] is not None and _step_counter[0] > _crash_after_step[0]:
        raise RuntimeError(
            f"[CRASH SIMULATION] Process crashing after step {_crash_after_step[0]}! "
            "Re-run to resume from Nexum checkpoint."
        )
    return submit_tool_call("visit_webpage", {"url": url}, session_id=_session_id[0])


# ── Agent setup ────────────────────────────────────────────────────

def make_agent(model_id: str, gemini_api_key: str | None) -> AssistantAgent:
    """Create an AutoGen AssistantAgent with Nexum-backed tools."""

    # OpenAIChatCompletionClient supports Gemini via the OpenAI-compatible endpoint
    if model_id.startswith("gemini/"):
        model_name = model_id[len("gemini/"):]
        model_client = OpenAIChatCompletionClient(
            model=model_name,
            api_key=gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    else:
        # Standard OpenAI-compatible endpoint
        model_client = OpenAIChatCompletionClient(model=model_id)

    tools = [
        FunctionTool(web_search, description="Search the web using DuckDuckGo."),
        FunctionTool(visit_webpage, description="Fetch and read the content of a webpage."),
    ]

    agent = AssistantAgent(
        name="research_assistant",
        model_client=model_client,
        tools=tools,
        system_message=(
            "You are a helpful research assistant. "
            "Use web_search to find information and visit_webpage to read pages in detail. "
            "Always provide a thorough, well-sourced answer."
        ),
    )
    return agent


async def run_agent(agent: AssistantAgent, query: str) -> None:
    """Run the agent and stream output to console."""
    await Console(agent.run_stream(task=query))


def main():
    parser = argparse.ArgumentParser(description="AutoGen + Nexum durable tool execution")
    parser.add_argument("query", help="Research question for the agent")
    parser.add_argument(
        "--crash-after-step",
        type=int,
        default=None,
        help="Simulate a crash after N tool calls complete (for crash-recovery demo)",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID for crash recovery (default: derived from query)",
    )
    args = parser.parse_args()

    # Deterministic session ID from query
    session_id = args.session_id or hashlib.sha256(args.query.encode()).hexdigest()[:12]

    # Set globals for tool wrappers
    _session_id[0] = session_id
    _crash_after_step[0] = args.crash_after_step

    # Model config
    model_id = os.environ.get("NEXUM_MODEL", "gemini/gemini-2.5-flash-preview-04-17")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")

    print(f"[AutoGen+Nexum] Session:  {session_id}")
    print(f"[AutoGen+Nexum] Query:    {args.query}")
    print(f"[AutoGen+Nexum] Model:    {model_id}")
    if args.crash_after_step is not None:
        print(f"[AutoGen+Nexum] Will crash after step {args.crash_after_step}")
    print()

    agent = make_agent(model_id, gemini_api_key)
    asyncio.run(run_agent(agent, args.query))


if __name__ == "__main__":
    main()
