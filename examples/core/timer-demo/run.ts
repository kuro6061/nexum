import { nexum, Worker, NexumClient } from 'nexum-js';
import { z } from 'zod';

// 3-step workflow: fetch data -> wait 5 seconds -> process result
const FetchResult = z.object({ data: z.string(), fetchedAt: z.string() });
const ProcessResult = z.object({ processed: z.string(), timerInfo: z.object({ waited_until: z.string(), delay_seconds: z.number() }) });

const timerWorkflow = nexum.workflow('TimerDemo')
  .effect('fetch', FetchResult, async (ctx) => {
    console.log('[WORKER] Fetching data...');
    await sleep(300);
    return { data: `Result for: ${ctx.input.query}`, fetchedAt: new Date().toISOString() };
  })
  .timer('wait', { delaySeconds: 5 })
  .compute('process', ProcessResult, (ctx) => {
    const fetchData = ctx.get('fetch');
    const timerData = ctx.get('wait');
    console.log('[WORKER] Processing after timer...');
    return {
      processed: `Processed: ${fetchData.data}`,
      timerInfo: timerData,
    };
  })
  .build();

async function main() {
  const client = new NexumClient();
  const worker = new Worker('localhost:50051', 'timer-worker-1');
  worker.register(timerWorkflow);

  console.log('\n=== NEXUM TIMER DEMO ===\n');

  await worker.start();

  const executionId = await client.startExecution(
    timerWorkflow.workflowId,
    timerWorkflow.versionHash,
    { query: 'timer test' }
  );
  console.log(`[NEXUM] Started execution: ${executionId}`);
  console.log('[NEXUM] Workflow: fetch -> timer(5s) -> process\n');

  // Poll for completion
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    const status = await client.getStatus(executionId);
    const completed = Object.keys(status.completedNodes ?? {});
    console.log(`[POLL] Status: ${status.status} | Completed: [${completed.join(', ')}]`);
    if (status.status === 'COMPLETED') {
      console.log('\n=== RESULT ===');
      console.log(JSON.stringify(status.completedNodes, null, 2));
      break;
    }
  }

  worker.stop();
  console.log('\n[DONE] Timer demo complete!');
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

main().catch(console.error);
