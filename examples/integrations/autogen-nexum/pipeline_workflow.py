"""
pipeline_workflow.py  E4-step multi-agent pipeline for AutoGen #7043 recovery demo.

Pipeline: research ↁEvalidate ↁEsummarize ↁEreport

Each step is an EFFECT node in Nexum. Crash between any two steps
and the workflow resumes exactly from where it left off.
"""

import sys
import os


from pydantic import BaseModel
from nexum import workflow


class StepOutput(BaseModel):
    step: str
    result: str


def _placeholder(ctx):
    raise RuntimeError("This handler runs in pipeline_worker.py, not here")


research_report_workflow = (
    workflow("autogen-research-pipeline")
    .effect("research",  StepOutput, handler=_placeholder, depends_on=[])
    .effect("validate",  StepOutput, handler=_placeholder, depends_on=["research"])
    .effect("summarize", StepOutput, handler=_placeholder, depends_on=["validate"])
    .effect("report",    StepOutput, handler=_placeholder, depends_on=["summarize"])
    .build()
)
