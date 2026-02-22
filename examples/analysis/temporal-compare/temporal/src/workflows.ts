import { proxyActivities, getVersion, DEFAULT_VERSION, log } from '@temporalio/workflow';
import type * as activities from './activities';

const { analyzeTopic, repairJson, extractFacts, checkConfidence, generateReport } =
  proxyActivities<typeof activities>({ startToCloseTimeout: '2 minutes', retry: { maximumAttempts: 3 } });

function isValidJson(s: string): boolean {
  try { JSON.parse(s); return true; } catch { return false; }
}

export async function llmRepairWorkflow(query: string): Promise<string> {
  // Step 1: Initial LLM call
  let rawJson = await analyzeTopic(query);

  // Step 2: Self-repair loop
  // ⚠️ TEMPORAL PROBLEM: This loop is non-deterministic.
  // If LLM behavior changes between original execution and Replay,
  // the loop iteration count may differ → WorkflowNondeterminismError
  // Solution: push ALL loop logic into a single Activity (loses visibility)
  let attempts = 0;
  while (!isValidJson(rawJson) && attempts < 3) {
    log.warn('JSON invalid, attempting repair', { attempt: attempts + 1 });
    rawJson = await repairJson(rawJson, query);
    attempts++;
  }

  // Step 3: Extract facts
  const facts = await extractFacts(rawJson);

  // ─── VERSION 2: Add confidence check ─────────────────────────────────
  // To add this step safely for IN-FLIGHT workflows, getVersion() is REQUIRED.
  // Every structural change must be wrapped. This accumulates over time.
  const version = await getVersion('add-confidence-check', DEFAULT_VERSION, 1);
  let confidence = 1.0;
  if (version >= 1) {
    confidence = await checkConfidence(rawJson);
    // ⚠️ If confidence is low, what do we do? Re-run repair?
    // That requires ANOTHER getVersion for the new branch:
    const v2 = await getVersion('low-confidence-repair', DEFAULT_VERSION, 1);
    if (v2 >= 1 && confidence < 0.8) {
      rawJson = await repairJson(rawJson, query + ' (low confidence retry)');
      confidence = await checkConfidence(rawJson); // called twice = double billing
    }
  }
  // ─────────────────────────────────────────────────────────────────────

  return await generateReport(facts, confidence);
}
