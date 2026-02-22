"""
worker.py - Nexum worker for ragas-nexum.

Implements LLM-as-Judge evaluation as a Nexum EFFECT node.

For each QA sample, evaluates two RAGAS-style metrics:
  - faithfulness:    Is the answer grounded in the provided context? (0.0 - 1.0)
  - answer_relevancy: Does the answer address the question? (0.0 - 1.0)

References:
  - RAGAS issue #2136: "Support for Batch API" (lower cost)
  - RAGAS issue #2105: "Generate QA samples in parallel for big batches"
  - RAGAS issue #2473: "Evaluation is slow despite high RPM limits"

Usage:
    PYTHONIOENCODING=utf-8 python worker.py
"""

import asyncio
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


class EvalResult(BaseModel):
    sample_id: str
    question: str
    faithfulness: float        # 0.0 - 1.0: answer grounded in context?
    answer_relevancy: float    # 0.0 - 1.0: answer relevant to question?
    faithfulness_reason: str
    relevancy_reason: str


def handle_evaluate(ctx) -> EvalResult:
    """
    LLM-as-Judge evaluation for a single QA sample.

    Input:
        sample_id (str): unique identifier
        question  (str): the user question
        answer    (str): the RAG pipeline's answer
        contexts  (list[str]): retrieved passages used to generate the answer

    Output:
        EvalResult with faithfulness and answer_relevancy scores
    """
    from openai import OpenAI

    sample_id = ctx.input["sample_id"]
    question = ctx.input["question"]
    answer = ctx.input["answer"]
    contexts = ctx.input["contexts"]

    logger.info(f"Evaluating sample: {sample_id}")

    context_text = "\n\n".join(f"[Context {i+1}]: {c}" for i, c in enumerate(contexts))

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    client = OpenAI(
        api_key=gemini_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    prompt = f"""You are a strict RAG evaluation judge. Evaluate the following QA sample on two metrics.

Question: {question}

Answer: {answer}

{context_text}

Evaluate on:
1. faithfulness (0.0-1.0): Is every claim in the answer directly supported by the context? 
   Score 1.0 if all claims are supported, 0.0 if the answer contradicts or ignores the context.
2. answer_relevancy (0.0-1.0): Does the answer directly address the question?
   Score 1.0 if the answer fully addresses the question, 0.0 if it is off-topic.

Respond in JSON only:
{{
  "faithfulness": <float>,
  "faithfulness_reason": "<one sentence>",
  "answer_relevancy": <float>,
  "relevancy_reason": "<one sentence>"
}}"""

    response = client.chat.completions.create(
        model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": "You are an expert RAG evaluation judge. Always respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        # Note: Gemini's json_object mode can produce slightly malformed JSON;
        # we parse defensively below.
    )

    raw = response.choices[0].message.content.strip()

    # Gemini sometimes wraps JSON in markdown fences  Estrip them
    if raw.startswith("```"):
        raw = "\n".join(
            line for line in raw.split("\n")
            if not line.strip().startswith("```")
        ).strip()

    # Try direct parse; fall back to extracting first {...} block
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
        else:
            raise RuntimeError(f"Could not parse JSON from Gemini response: {raw[:200]}")

    result = EvalResult(
        sample_id=sample_id,
        question=question,
        faithfulness=float(data.get("faithfulness", 0.0)),
        answer_relevancy=float(data.get("answer_relevancy", 0.0)),
        faithfulness_reason=data.get("faithfulness_reason", ""),
        relevancy_reason=data.get("relevancy_reason", ""),
    )
    logger.info(
        f"[{sample_id}] faithfulness={result.faithfulness:.2f} "
        f"relevancy={result.answer_relevancy:.2f}"
    )
    return result


# --- Workflow definition ---
eval_workflow = (
    workflow("ragas-eval")
    .effect("evaluate", EvalResult, handler=handle_evaluate, depends_on=[])
    .build()
)


async def main():
    client = NexumClient()
    compat = client.register_workflow(eval_workflow)
    logger.info(f"Registered workflow: {eval_workflow.workflow_id} (compatibility: {compat})")
    logger.info("Worker started. Waiting for tasks on localhost:50051 ...")
    w = Worker([eval_workflow], concurrency=8, poll_interval=0.1)
    w._running = True
    await w._run()


if __name__ == "__main__":
    asyncio.run(main())
