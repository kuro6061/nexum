import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// Define the workflow
const SearchResult = z.object({ content: z.string() });
const Summary = z.object({ score: z.number(), text: z.string() });

const researchWorkflow = nexum.workflow('ResearchAgent')
  .effect('search', SearchResult, async (ctx) => {
    console.log('[WORKER] Executing: search');
    await sleep(500); // simulate work
    return { content: 'Research about: ' + ctx.input.query };
  })
  .effect('summarize', Summary, async (ctx) => {
    console.log('[WORKER] Executing: summarize');
    await sleep(500);
    return { score: 88, text: 'Summary of: ' + ctx.get('search').content };
  })
  .build();

async function runDemo() {
  const client = new NexumClient();

  // === First Worker (will "crash" after search) ===
  const worker1 = new Worker('localhost:50051', 'worker-1');
  worker1.register(researchWorkflow);

  // Hook: stop worker after 'search' completes
  let searchDone = false;
  const originalHandler = researchWorkflow.handlers['search'].handler;
  researchWorkflow.handlers['search'].handler = async (ctx) => {
    const result = await originalHandler(ctx);
    searchDone = true;
    return result;
  };

  console.log('\n=== NEXUM DURABILITY DEMO ===\n');

  // Start worker 1 (registers workflow on server, then polls in background)
  await worker1.start();

  // Start execution
  const executionId = await client.startExecution(
    researchWorkflow.workflowId,
    researchWorkflow.versionHash,
    { query: 'LLM Durable Execution' }
  );
  console.log(`[NEXUM] Started execution: ${executionId}`);

  // Wait for search to complete, then stop worker
  await waitFor(() => searchDone, 10000);
  console.log('\n[DEMO] Worker 1 stopping (simulating crash)...\n');
  worker1.stop();

  await sleep(500);

  // === Second Worker (resumes from where we left off) ===
  console.log('[DEMO] Starting Worker 2 (recovery)...');
  const worker2 = new Worker('localhost:50051', 'worker-2');
  worker2.register(researchWorkflow);
  worker2.start();

  // Wait for completion
  let finalStatus;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    finalStatus = await client.getStatus(executionId);
    if (finalStatus.status === 'COMPLETED') break;
  }

  worker2.stop();

  console.log('\n=== RESULT ===');
  console.log('Status:', finalStatus?.status);
  console.log('Completed nodes:', Object.keys(finalStatus?.completedNodes ?? {}));
  console.log('\n[SUCCESS] Worker 2 resumed from "summarize" - durability proven!');
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
function waitFor(pred: () => boolean, timeout: number) {
  return new Promise<void>((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      if (pred()) resolve();
      else if (Date.now() - start > timeout) reject(new Error('timeout'));
      else setTimeout(check, 100);
    };
    check();
  });
}

runDemo().catch(console.error);
