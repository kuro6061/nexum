import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// Schema definitions
const AnalysisResult = z.object({
  data: z.string(),
  is_valid: z.boolean(),
  score: z.number(),
  attempt: z.number(),
});

const ValidationResult = z.object({
  is_valid: z.boolean(),
  score: z.number(),
});

const RepairResult = z.object({
  fixed_data: z.string(),
});

const FinalReport = z.object({
  report: z.string(),
  score: z.number(),
});

// --- Scenario 1: Invalid data → routes to 'repair' ---
const invalidWorkflow = nexum.workflow<{ text: string }>('SelfRepairAgent-Invalid')
  .effect('analyze', AnalysisResult, async (ctx) => {
    console.log('  [ANALYZE] Processing text (will fail validation)...');
    return { data: 'broken analysis', is_valid: false, score: 0.4, attempt: 0 };
  })
  .computeAfter('validate', ['analyze'], ValidationResult, (ctx) => {
    const analysis = ctx.get('analyze');
    return { is_valid: analysis.is_valid && analysis.score > 0.7, score: analysis.score };
  })
  .routerAfter('route_decision', ['validate'], [
    { condition: '$.is_valid == true', target: 'report' },
    { condition: '$.is_valid == false', target: 'repair' },
  ], (ctx) => {
    const valid = ctx.get('validate');
    return { routed_to: valid.is_valid ? 'report' : 'repair' };
  })
  .effectAfter('repair', ['analyze', 'validate', 'route_decision'], RepairResult, async (ctx) => {
    console.log('  [REPAIR] Score was low, repairing...');
    return { fixed_data: 'repaired: ' + ctx.get('analyze').data };
  })
  .effectAfter('report', ['analyze', 'validate', 'route_decision'], FinalReport, async (ctx) => {
    return {
      report: 'Valid analysis: ' + ctx.get('analyze').data,
      score: ctx.get('validate').score,
    };
  })
  .build();

// --- Scenario 2: Valid data → routes to 'report' ---
const validWorkflow = nexum.workflow<{ text: string }>('SelfRepairAgent-Valid')
  .effect('analyze', AnalysisResult, async (ctx) => {
    console.log('  [ANALYZE] Processing text (will pass validation)...');
    return { data: 'good analysis', is_valid: true, score: 0.9, attempt: 1 };
  })
  .computeAfter('validate', ['analyze'], ValidationResult, (ctx) => {
    const analysis = ctx.get('analyze');
    return { is_valid: analysis.is_valid && analysis.score > 0.7, score: analysis.score };
  })
  .routerAfter('route_decision', ['validate'], [
    { condition: '$.is_valid == true', target: 'report' },
    { condition: '$.is_valid == false', target: 'repair' },
  ], (ctx) => {
    const valid = ctx.get('validate');
    return { routed_to: valid.is_valid ? 'report' : 'repair' };
  })
  .effectAfter('repair', ['analyze', 'validate', 'route_decision'], RepairResult, async (ctx) => {
    console.log('  [REPAIR] Score was low, repairing...');
    return { fixed_data: 'repaired: ' + ctx.get('analyze').data };
  })
  .effectAfter('report', ['analyze', 'validate', 'route_decision'], FinalReport, async (ctx) => {
    console.log('  [REPORT] Generating final report...');
    return {
      report: 'Valid analysis: ' + ctx.get('analyze').data,
      score: ctx.get('validate').score,
    };
  })
  .build();

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

async function runDemo() {
  const client = new NexumClient();

  console.log('\n=== NEXUM ROUTER DEMO ===\n');

  // --- Run 1: Invalid path ---
  console.log('--- Scenario 1: Invalid data (should route to REPAIR) ---\n');
  const worker1 = new Worker('localhost:50051', 'router-worker-1');
  worker1.register(invalidWorkflow);
  await worker1.start();

  const exec1 = await client.startExecution(
    invalidWorkflow.workflowId,
    invalidWorkflow.versionHash,
    { text: 'analyze this poorly' }
  );
  console.log(`  Started execution: ${exec1}`);

  let status1;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    status1 = await client.getStatus(exec1);
    if (status1.status === 'COMPLETED') break;
  }
  worker1.stop();

  console.log(`\n  Status: ${status1?.status}`);
  console.log(`  Completed nodes: ${Object.keys(status1?.completedNodes ?? {}).join(', ')}`);
  const hasRepair = status1?.completedNodes?.repair !== undefined;
  const hasReport1 = status1?.completedNodes?.report !== undefined;
  console.log(`  Routed to repair: ${hasRepair}, Routed to report: ${hasReport1}`);

  await sleep(500);

  // --- Run 2: Valid path ---
  console.log('\n--- Scenario 2: Valid data (should route to REPORT) ---\n');
  const worker2 = new Worker('localhost:50051', 'router-worker-2');
  worker2.register(validWorkflow);
  await worker2.start();

  const exec2 = await client.startExecution(
    validWorkflow.workflowId,
    validWorkflow.versionHash,
    { text: 'analyze this well' }
  );
  console.log(`  Started execution: ${exec2}`);

  let status2;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    status2 = await client.getStatus(exec2);
    if (status2.status === 'COMPLETED') break;
  }
  worker2.stop();

  console.log(`\n  Status: ${status2?.status}`);
  console.log(`  Completed nodes: ${Object.keys(status2?.completedNodes ?? {}).join(', ')}`);
  const hasRepair2 = status2?.completedNodes?.repair !== undefined;
  const hasReport2 = status2?.completedNodes?.report !== undefined;
  console.log(`  Routed to repair: ${hasRepair2}, Routed to report: ${hasReport2}`);

  // Summary
  console.log('\n=== RESULTS ===');
  console.log(`  Scenario 1 (invalid): ${hasRepair ? 'REPAIR' : 'REPORT'} path taken ${status1?.status === 'COMPLETED' ? '[OK]' : '[FAIL]'}`);
  console.log(`  Scenario 2 (valid):   ${hasReport2 ? 'REPORT' : 'REPAIR'} path taken ${status2?.status === 'COMPLETED' ? '[OK]' : '[FAIL]'}`);

  if (hasRepair && !hasReport1 && hasReport2 && !hasRepair2) {
    console.log('\n  [SUCCESS] ROUTER conditional branching works correctly!');
  } else {
    console.log('\n  [ISSUE] Routing did not match expected paths.');
  }
}

runDemo().catch(console.error);
