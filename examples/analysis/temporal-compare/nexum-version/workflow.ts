// EVERYTHING in one file - no artificial separation required
import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// Schemas
const AnalysisResult = z.object({ facts: z.array(z.string()), confidence: z.number(), rawJson: z.string() });
const RepairedResult  = z.object({ facts: z.array(z.string()), confidence: z.number(), repairCount: z.number() });
const ConfidenceCheck = z.object({ passed: z.boolean(), score: z.number() });  // V2: new step
const FinalReport     = z.object({ report: z.string(), confidence: z.number() });

function isValidJson(s: string) { try { JSON.parse(s); return true; } catch { return false; } }

const llmRepairWorkflow = nexum.workflow('LlmRepairAgent')

  // Step 1: Analyze (LLM call - may return broken JSON)
  .effect('analyze', AnalysisResult, async (ctx) => {
    const responses = [
      `{"facts": ["LLM agents need durability", "crash recovery is critical"], "confidence": 0.9}`,
      `{"facts": ["event sourcing enables replay"  "idempotency prevents duplication"}, "confidence": 0.85`,
    ];
    const raw = responses[Math.floor(Math.random() * responses.length)];
    await sleep(300);
    const valid = isValidJson(raw) ? raw : `{"facts":["${ctx.input.query} needs durability"],"confidence":0.75}`;
    const p = JSON.parse(valid);
    return { facts: p.facts, confidence: p.confidence, rawJson: raw };
  })

  // Step 2: Repair if needed (idempotency key = same input → same output, no duplicate calls)
  // No non-determinism problem: each repair attempt is a SEPARATE tracked node.
  // No getVersion needed: this node exists in V1 and V2 alike.
  .effect('repair_if_needed', RepairedResult, async (ctx) => {
    const analysis = ctx.get('analyze');
    if (isValidJson(analysis.rawJson)) {
      return { facts: analysis.facts, confidence: analysis.confidence, repairCount: 0 };
    }
    await sleep(200);
    return { facts: [`repaired: ${ctx.input.query} requires durable execution`], confidence: 0.75, repairCount: 1 };
  })

  // ─── VERSION 2: Add confidence check ─────────────────────────────────
  // Just add 4 lines. No getVersion. No risk to in-flight workflows.
  // Nexum detects version hash change → routes new executions to V2 worker.
  // Old executions continue on V1 worker without modification.
  .compute('confidence_check', ConfidenceCheck, (ctx) => {
    const repaired = ctx.get('repair_if_needed');
    return { passed: repaired.confidence >= 0.8, score: repaired.confidence };
  })
  // ─────────────────────────────────────────────────────────────────────

  // Step 3: Generate report
  .effect('generate_report', FinalReport, async (ctx) => {
    const repaired = ctx.get('repair_if_needed');
    const check    = ctx.get('confidence_check');
    await sleep(200);
    return {
      report: `Report (${check.passed ? '✓' : '⚠ low confidence'}): ${repaired.facts.join('; ')}`,
      confidence: repaired.score,
    };
  })

  .build();

// Worker + Client setup: same as always (~15 lines)
async function run() {
  const client = new NexumClient();
  const worker = new Worker('localhost:50051', 'worker-1');
  worker.register(llmRepairWorkflow);
  await worker.start();

  const execId = await client.startExecution(
    llmRepairWorkflow.workflowId,
    llmRepairWorkflow.versionHash,
    { query: 'durable execution for LLM agents' }
  );

  let status: any;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    status = await client.getStatus(execId);
    if (status.status === 'COMPLETED') break;
  }
  worker.stop();

  const report = status?.completedNodes?.['generate_report'];
  console.log('Result:', report?.report ?? report);
  console.log('Confidence:', report?.confidence);
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
run().catch(console.error);
