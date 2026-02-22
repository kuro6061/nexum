import { Client, Connection } from '@temporalio/client';
import { llmRepairWorkflow } from './workflows';

async function run() {
  const connection = await Connection.connect({ address: 'localhost:7233' });
  const client = new Client({ connection });

  const handle = await client.workflow.start(llmRepairWorkflow, {
    taskQueue: 'llm-repair-queue',
    workflowId: `llm-repair-${Date.now()}`,
    args: ['durable execution for LLM agents'],
  });

  console.log('Started workflow:', handle.workflowId);
  const result = await handle.result();
  console.log('Result:', result);
}
run().catch(console.error);
