"""
demo.py — smolagents ToolCallingAgent with durable Nexum tool execution.

Each tool call the LLM decides to make is submitted as a Nexum workflow,
giving crash-recovery and retry semantics for free.

Usage:
    python demo.py "What is the population of Tokyo vs New York?"
    python demo.py --crash-after-step 1 "What is the population of Tokyo?"
    python demo.py --session-id my-session "reuse previous results"
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "packages", "sdk-python"))

from smolagents import Tool, ToolCallingAgent, LiteLLMModel, DuckDuckGoSearchTool, VisitWebpageTool

from submit_task import submit_tool_call


# ── Nexum-backed tool wrappers ──────────────────────────────────────
# These wrap the real smolagents tools so that every call goes through
# Nexum instead of being executed in-process.


class NexumDuckDuckGoSearchTool(Tool):
    name = "web_search"
    description = (
        "Performs a duckduckgo web search based on your query "
        "(think a Google search) then returns the top search results."
    )
    inputs = {"query": {"type": "string", "description": "The search query to perform."}}
    output_type = "string"

    def __init__(self, session_id: str, crash_after_step: int | None, step_counter: list):
        super().__init__()
        self._session_id = session_id
        self._crash_after_step = crash_after_step
        self._step_counter = step_counter
        self.is_initialized = True

    def forward(self, query: str) -> str:
        self._step_counter[0] += 1
        if self._crash_after_step is not None and self._step_counter[0] > self._crash_after_step:
            raise RuntimeError(
                f"[CRASH SIMULATION] Process crashing after step {self._crash_after_step}! "
                "Re-run to resume from Nexum checkpoint."
            )
        return submit_tool_call("web_search", {"query": query}, session_id=self._session_id)


class NexumVisitWebpageTool(Tool):
    name = "visit_webpage"
    description = (
        "Visits a webpage at the given url and reads its content as a markdown string. "
        "Use this to browse webpages."
    )
    inputs = {"url": {"type": "string", "description": "The url of the webpage to visit."}}
    output_type = "string"

    def __init__(self, session_id: str, crash_after_step: int | None, step_counter: list):
        super().__init__()
        self._session_id = session_id
        self._crash_after_step = crash_after_step
        self._step_counter = step_counter
        self.is_initialized = True

    def forward(self, url: str) -> str:
        self._step_counter[0] += 1
        if self._crash_after_step is not None and self._step_counter[0] > self._crash_after_step:
            raise RuntimeError(
                f"[CRASH SIMULATION] Process crashing after step {self._crash_after_step}! "
                "Re-run to resume from Nexum checkpoint."
            )
        return submit_tool_call("visit_webpage", {"url": url}, session_id=self._session_id)


def main():
    parser = argparse.ArgumentParser(description="smolagents + Nexum durable tool execution")
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

    # Deterministic session ID from query so re-runs reuse the same session
    session_id = args.session_id or hashlib.sha256(args.query.encode()).hexdigest()[:12]

    # Mutable counter shared across tools to track total steps
    step_counter = [0]

    # Create Nexum-backed tools
    tools = [
        NexumDuckDuckGoSearchTool(session_id, args.crash_after_step, step_counter),
        NexumVisitWebpageTool(session_id, args.crash_after_step, step_counter),
    ]

    # LLM backend — uses LiteLLM to route to Anthropic Claude
    model = LiteLLMModel(
        model_id="anthropic/claude-haiku-3-5-20241022",
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )

    agent = ToolCallingAgent(
        tools=tools,
        model=model,
        max_steps=10,
    )

    print(f"[smolagents] Session: {session_id}")
    print(f"[smolagents] Query: {args.query}")
    if args.crash_after_step is not None:
        print(f"[smolagents] Will crash after step {args.crash_after_step}")
    print()

    result = agent.run(args.query)

    print()
    print(f"Final Answer: {result}")


if __name__ == "__main__":
    main()
