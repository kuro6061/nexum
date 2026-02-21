import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// Schemas
const ParsedQuery = z.object({ topic: z.string() });
const TechResults = z.object({ data: z.string() });
const MarketResults = z.object({ data: z.string() });
const MergedResults = z.object({ combined: z.string() });
const Report = z.object({ report: z.string() });

/**
 * Fan-out / Fan-in workflow:
 *
 *   parse
 *     |
 *     +---> search_tech   (parallel, depends only on parse)
 *     +---> search_market  (parallel, depends only on parse)
 *     |
 *     v
 *   merge (depends on BOTH search_tech AND search_market)
 *     |
 *     v
 *   final_report
 */
const parallelWorkflow = nexum.workflow('ParallelResearch')
  .compute('parse', ParsedQuery, ctx => {
    console.log('[WORKER] Executing: parse');
    return { topic: ctx.input.query };
  })

  // Fan-out: both depend ONLY on 'parse' (not on each other)
  .effectAfter('search_tech', ['parse'], TechResults, async ctx => {
    console.log('[WORKER] Executing: search_tech (starts now)');
    const start = Date.now();
    await sleep(500);
    console.log(`[WORKER] search_tech done in ${Date.now() - start}ms`);
    return { data: `Tech findings on: ${ctx.get('parse').topic}` };
  })
  .effectAfter('search_market', ['parse'], MarketResults, async ctx => {
    console.log('[WORKER] Executing: search_market (starts now)');
    const start = Date.now();
    await sleep(700);
    console.log(`[WORKER] search_market done in ${Date.now() - start}ms`);
    return { data: `Market findings on: ${ctx.get('parse').topic}` };
  })

  // Fan-in: depends on BOTH parallel branches
  .computeAfter('merge', ['search_tech', 'search_market'], MergedResults, ctx => {
    console.log('[WORKER] Executing: merge');
    return { combined: `${ctx.get('search_tech').data} | ${ctx.get('search_market').data}` };
  })

  .effect('final_report', Report, async ctx => {
    console.log('[WORKER] Executing: final_report');
    return { report: `Final: ${ctx.get('merge').combined}` };
  })

  .build();

async function runDemo() {
  const client = new NexumClient();
  const worker = new Worker('localhost:50051', 'parallel-worker-1');
  worker.register(parallelWorkflow);

  console.log('\n=== NEXUM PARALLEL EXECUTION DEMO ===\n');
  console.log('Workflow graph:');
  console.log('  parse');
  console.log('    |');
  console.log('    +---> search_tech   (500ms)');
  console.log('    +---> search_market  (700ms)');
  console.log('    |');
  console.log('    v');
  console.log('  merge (fan-in)');
  console.log('    |');
  console.log('    v');
  console.log('  final_report\n');

  await worker.start();

  const overallStart = Date.now();
  const executionId = await client.startExecution(
    parallelWorkflow.workflowId,
    parallelWorkflow.versionHash,
    { query: 'AI Infrastructure' }
  );
  console.log(`[NEXUM] Started execution: ${executionId}\n`);

  // Wait for completion
  let finalStatus;
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    finalStatus = await client.getStatus(executionId);
    if (finalStatus.status === 'COMPLETED') break;
  }

  const elapsed = Date.now() - overallStart;
  worker.stop();

  console.log('\n=== RESULT ===');
  console.log('Status:', finalStatus?.status);
  console.log('Completed nodes:', Object.keys(finalStatus?.completedNodes ?? {}));
  console.log(`Total time: ${elapsed}ms`);
  console.log('\nIf search_tech (500ms) and search_market (700ms) ran in parallel,');
  console.log('the parallel section took ~700ms instead of ~1200ms sequential.');
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

runDemo().catch(console.error);
