import { Worker } from '@temporalio/worker';
import * as activities from './activities';

async function run() {
  const worker = await Worker.create({
    workflowsPath: require.resolve('./workflows'),
    activities,
    taskQueue: 'llm-repair-queue',
    // Large LLM payloads require custom DataConverter:
    // dataConverter: new LargePayloadDataConverter({ maxSize: 10 * 1024 * 1024 }),
    // ↑ Without this, any response > ~2MB causes silent data truncation
  });
  console.log('Temporal worker started');
  await worker.run();
}
run().catch(e => { console.error(e); process.exit(1); });
