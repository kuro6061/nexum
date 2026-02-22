"""
Nexum workflow for browser-use tasks.

A multi-step research pipeline where each step uses browser-use:
  research → summarize → follow_up → report

Each browser-use Agent.run() is an EFFECT node — if the process crashes,
Nexum resumes from the last completed browser task.
"""

from pydantic import BaseModel
from nexum import workflow


class BrowseResult(BaseModel):
    content: str
    url: str = ""


class Summary(BaseModel):
    text: str
    key_points: list[str]


class Report(BaseModel):
    title: str
    content: str
    sources: list[str]


def _browser_handler(ctx):
    raise RuntimeError("Executed by worker.py")


def _compute_handler(ctx):
    raise RuntimeError("Executed by worker.py")


browser_research_workflow = (
    workflow("browser-research")
    .effect("research", BrowseResult, handler=_browser_handler, depends_on=[])
    .compute("summarize", Summary, handler=_compute_handler, depends_on=["research"])
    .effect("follow_up", BrowseResult, handler=_browser_handler, depends_on=["summarize"])
    .compute("report", Report, handler=_compute_handler, depends_on=["research", "summarize", "follow_up"])
    .build()
)
