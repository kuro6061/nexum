# Temporal vs Nexum: LLM Self-Repair Loop — Quantitative Comparison

## Scenario

Both implementations solve the same problem: an LLM agent that analyzes a topic,
self-repairs broken JSON output (up to 3 attempts), extracts facts, and generates
a report. Version 2 adds a confidence-check step between extraction and reporting.

---

## Line Counts (measured)

| File | Lines | Category |
|------|------:|----------|
| **Temporal** | | |
| `temporal/src/activities.ts` | 34 | Business logic |
| `temporal/src/workflows.ts` | 48 | Orchestration |
| `temporal/src/worker.ts` | 16 | Infrastructure |
| `temporal/src/client.ts` | 18 | Infrastructure |
| `temporal/src/data-converter.ts` | 11 (stub) / ~150 (full) | Infrastructure |
| `temporal/tsconfig.json` | 12 | Config |
| `temporal/package.json` | 21 | Config |
| **Temporal total** | **160 (shown) / ~299 (real)** | |
| | | |
| **Nexum** | | |
| `nexum-version/workflow.ts` | 90 | Everything |
| `nexum-version/package.json` | 16 | Config |
| **Nexum total** | **106** | |

---

## Side-by-Side Metrics

| Metric | Temporal | Nexum |
|--------|----------|-------|
| File count | 7 | 2 |
| Business logic lines | 34 | 40 |
| Orchestration lines | 48 | 35 |
| Infrastructure lines | 45 (stub) / ~184 (real) | 15 |
| Config lines | 33 | 16 |
| **Total lines** | **160 / ~299** | **106** |
| Boilerplate ratio | 49% (stub) / 73% (real) | 15% |
| `getVersion` calls for V1→V2 | 2 | 0 |
| New files needed for V2 | 0 (but workflow grows) | 0 (4 lines added) |
| Non-determinism risk | **HIGH** | **LOW** |
| LLM payload > 2MB handling | Manual (~150 lines + Codec Server) | Automatic |

> **Boilerplate ratio** = (infrastructure + config lines) / total lines

---

## The Non-Determinism Trap

Temporal workflows must be **deterministic on replay**. The self-repair loop in
`workflows.ts` is a latent bug:

```typescript
// Temporal: this loop is non-deterministic
while (!isValidJson(rawJson) && attempts < 3) {
  rawJson = await repairJson(rawJson, query);   // Activity call recorded in history
  attempts++;
}
```

If the LLM returns valid JSON on the original run (0 loop iterations) but broken
JSON on replay (1+ iterations), Temporal throws `WorkflowNondeterminismError`.
The "fix" is to push the entire loop into a single Activity — which **hides** the
individual repair attempts from the execution history and makes debugging harder.

Nexum avoids this entirely: each step is a separate tracked node with its own
idempotency key. The graph structure is deterministic even when individual node
outputs are non-deterministic.

---

## The `getVersion` Accumulation Problem

Adding one step (confidence check) required **two** `getVersion` calls in the
Temporal workflow. Here's what it looks like after 5 versions:

```typescript
// Temporal: after 5 versions of changes
const v1 = await getVersion('add-confidence-check', DEFAULT_VERSION, 1);
if (v1 >= 1) {
  const v2 = await getVersion('low-confidence-repair', DEFAULT_VERSION, 1);
  if (v2 >= 1 && confidence < 0.8) { /* ... */ }
}
const v3 = await getVersion('add-source-citation', DEFAULT_VERSION, 1);
if (v3 >= 1) { /* ... */ }
const v4 = await getVersion('add-hallucination-check', DEFAULT_VERSION, 1);
if (v4 >= 1) {
  const v5 = await getVersion('hallucination-retry', DEFAULT_VERSION, 1);
  if (v5 >= 1) { /* ... */ }
}
const v6 = await getVersion('add-token-counting', DEFAULT_VERSION, 1);
if (v6 >= 1) { /* ... */ }
// ... every version adds more branches, none can ever be removed
// because in-flight workflows may still be replaying through old paths
```

In Nexum, version 5 is just the current graph definition. Old executions run on
old workers; new executions run on new workers. No branching accumulates.

---

## The DataConverter Complexity

Temporal's default payload limit is ~2MB. LLM outputs from long-context models
(128k+ tokens) routinely exceed this. The solution requires:

1. Implement the "Claim Check" pattern (~150 lines of S3/GCS integration)
2. Deploy a separate **Codec Server** process
3. Configure AWS IAM roles and S3 bucket policies
4. Handle encode/decode for every payload in both directions
5. Update the Worker configuration to use the custom converter

Nexum handles large payloads automatically — the gRPC transport and storage
layer manage payload sizes without developer intervention.

---

## Summary

For LLM agent workflows specifically, Temporal's replay-based determinism model
creates friction at three levels:

1. **Non-determinism in LLM loops** — LLM outputs are inherently variable, making
   replay-safe loops difficult to write correctly
2. **Version accumulation** — each workflow change adds permanent branching that
   can never be cleaned up
3. **Payload limits** — LLM outputs frequently exceed default limits, requiring
   significant infrastructure work

Nexum's DAG-based model sidesteps all three: nodes are independently tracked,
versioning is hash-based with automatic routing, and payload handling is built in.
