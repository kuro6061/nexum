# RAGAS-style Evaluation + Nexum

LLM-as-Judge evaluation with crash recovery, parallel execution, and zero-cost re-evaluation.

Directly addresses open RAGAS issues:
- [#2473](https://github.com/vibrantlabsai/ragas/issues/2473): "RAGAS Evaluation Extremely Slow — 838 calls in 10 min despite 5k RPM" → Nexum parallel EFFECTs
- [#2136](https://github.com/vibrantlabsai/ragas/issues/2136): "Support for Batch API (lower cost)" → Nexum cache = $0 re-evaluation
- [#2105](https://github.com/vibrantlabsai/ragas/issues/2105): "Generate QA samples in parallel for big batches" → Nexum parallel EFFECT nodes

## The Problem

Running LLM-as-Judge evaluation for a large test set is:
- **Slow**: sequential evaluation = total time × N samples
- **Expensive**: each sample costs an LLM API call
- **Fragile**: crash at sample 500/838 → lose all results, restart from scratch

## Architecture

```
evaluate(samples=838)
  │
  ├─ EFFECT: evaluate(q01)  ┐
  ├─ EFFECT: evaluate(q02)  │  parallel, durable
  ├─ EFFECT: evaluate(q03)  │  LLM-as-Judge (faithfulness + answer_relevancy)
  ├─ ...                    │
  └─ EFFECT: evaluate(q838) ┘
  │
  └─ aggregate metrics (local, free)
```

Each EFFECT node:
1. Sends (question, answer, contexts) to Gemini for scoring
2. Returns `faithfulness` and `answer_relevancy` scores (0.0–1.0)
3. Result checkpointed in SQLite

## LLM Cost Comparison

| Scenario | LLM calls | Cost |
|---|---|---|
| Plain sequential (838 samples) | 838 | $$ |
| Nexum fresh run (838 samples) | 838 | $$ |
| Nexum re-evaluation (same session) | **0** | **$0** |
| Crash at sample 500, resume | **338** | **60% saved** |

## Metrics Evaluated

| Metric | Description |
|---|---|
| `faithfulness` | Are all claims in the answer grounded in the retrieved context? |
| `answer_relevancy` | Does the answer directly address the question? |

## Dataset

`dataset.py` contains 15 QA samples with intentional errors:
- `q04`: BST search complexity stated as O(n) instead of O(log n) → low faithfulness expected
- `q06`: Gradient descent direction stated as "steepest ascent" → low faithfulness expected
- `q08`: REST stated as "stateful" → low faithfulness expected

## Setup

```bash
pip install nexum openai
export GEMINI_API_KEY="your-key"
```

## Usage

### 1. Start the Nexum server
```bash
nexum dev
```

### 2. Start the worker
```bash
PYTHONIOENCODING=utf-8 python worker.py
```

### 3. Run evaluations
```bash
# Evaluate all 15 samples
PYTHONIOENCODING=utf-8 python evaluator.py

# Evaluate first 5, with 4 workers
PYTHONIOENCODING=utf-8 python evaluator.py --samples 5 --workers 4
```

### 4. Run the benchmark
```bash
PYTHONIOENCODING=utf-8 python benchmark.py --samples 8 --crash-after 3
```

## Files

| File | Purpose |
|---|---|
| `dataset.py` | 15 QA samples with some intentional faithfulness errors |
| `worker.py` | Nexum worker: `evaluate` EFFECT (LLM-as-Judge via Gemini) |
| `evaluator.py` | Client: submit parallel evaluations, collect scores |
| `benchmark.py` | 4-part benchmark: plain vs Nexum vs cached vs crash recovery |
