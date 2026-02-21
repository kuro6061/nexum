import { nexum, Worker } from '@nexum/sdk';
import { z } from 'zod';

const ParseResult = z.object({ topic: z.string() });
const Analysis = z.object({ findings: z.string() });
const Report = z.object({ report: z.string() });
const Validation = z.object({ valid: z.boolean() });
const Archive = z.object({ archived: z.boolean() });

// V1: parse -> analyze -> report
const workflowV1 = nexum.workflow('VersionedResearch')
  .compute('parse', ParseResult, ctx => ({ topic: ctx.input.query }))
  .effect('analyze', Analysis, async ctx => ({ findings: `Analysis of ${ctx.get('parse').topic}` }))
  .effect('report', Report, async ctx => ({ report: `Report: ${ctx.get('analyze').findings}` }))
  .build();

// V2: parse -> analyze -> validate -> report (inserted node, changed report deps = BREAKING)
const workflowV2 = nexum.workflow('VersionedResearch')
  .compute('parse', ParseResult, ctx => ({ topic: ctx.input.query }))
  .effect('analyze', Analysis, async ctx => ({ findings: `Analysis of ${ctx.get('parse').topic}` }))
  .effect('validate', Validation, async ctx => ({ valid: true }))
  .effect('report', Report, async ctx => ({ report: `Report: ${ctx.get('analyze').findings}` }))
  .build();

// V3: parse -> analyze -> report -> archive (added leaf node = SAFE)
const workflowV3 = nexum.workflow('VersionedResearch')
  .compute('parse', ParseResult, ctx => ({ topic: ctx.input.query }))
  .effect('analyze', Analysis, async ctx => ({ findings: `Analysis of ${ctx.get('parse').topic}` }))
  .effect('report', Report, async ctx => ({ report: `Report: ${ctx.get('analyze').findings}` }))
  .effect('archive', Archive, async ctx => ({ archived: true }))
  .build();

async function runDemo() {
  console.log('\n=== NEXUM VERSION COMPATIBILITY DEMO ===\n');

  // Register V1 (NEW)
  console.log('--- Registering V1 (parse -> analyze -> report) ---');
  const worker1 = new Worker('localhost:50051', 'v-worker-1');
  worker1.register(workflowV1);
  await worker1.start();
  worker1.stop();

  await sleep(500);

  // Register V2 (BREAKING: node inserted, dependencies changed)
  console.log('\n--- Registering V2 (parse -> analyze -> validate -> report) ---');
  const worker2 = new Worker('localhost:50051', 'v-worker-2');
  worker2.register(workflowV2);
  await worker2.start();
  worker2.stop();

  await sleep(500);

  // Register V3: compared against V2 (latest), V3 lacks 'validate' => BREAKING
  console.log('\n--- Registering V3 (parse -> analyze -> report -> archive) ---');
  console.log('    (compared to V2 which has "validate" node that V3 lacks)');
  const worker3 = new Worker('localhost:50051', 'v-worker-3');
  worker3.register(workflowV3);
  await worker3.start();
  worker3.stop();

  await sleep(500);

  // Register V1 again: compared against V3 (latest), V1 lacks 'archive' => BREAKING
  // To show SAFE: build V3b that adds to V3
  const ArchiveExtra = z.object({ summary: z.string() });
  const workflowV3b = nexum.workflow('VersionedResearch')
    .compute('parse', ParseResult, ctx => ({ topic: ctx.input.query }))
    .effect('analyze', Analysis, async ctx => ({ findings: `Analysis of ${ctx.get('parse').topic}` }))
    .effect('report', Report, async ctx => ({ report: `Report: ${ctx.get('analyze').findings}` }))
    .effect('archive', Archive, async ctx => ({ archived: true }))
    .effect('summarize', ArchiveExtra, async ctx => ({ summary: 'Final summary' }))
    .build();

  console.log('\n--- Registering V3b (V3 + summarize node) ---');
  console.log('    (adds "summarize" node to V3, all old nodes unchanged => SAFE)');
  const worker4 = new Worker('localhost:50051', 'v-worker-4');
  worker4.register(workflowV3b);
  await worker4.start();
  worker4.stop();

  console.log('\n=== DEMO COMPLETE ===');
  console.log('Expected output:');
  console.log('  V1: NEW (first registration)');
  console.log('  V2: BREAKING (dependencies changed for "report")');
  console.log('  V3: BREAKING (V2 had "validate", V3 does not)');
  console.log('  V3b: SAFE (adds "summarize" to V3, all V3 nodes unchanged)');
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

runDemo().catch(console.error);
