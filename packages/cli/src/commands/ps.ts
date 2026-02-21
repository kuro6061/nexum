import { parseArgs } from 'node:util';
import { NexumClient } from '@nexum/sdk';

const { values } = parseArgs({
  options: {
    workflow: { type: 'string' },
    status: { type: 'string' },
    limit: { type: 'string', default: '20' },
  },
  allowPositionals: true,
});

const client = new NexumClient();
const executions = await client.listExecutions({
  workflowId: values.workflow,
  status: values.status,
  limit: parseInt(values.limit ?? '20'),
});

if (executions.length === 0) {
  console.log('No executions found.');
} else {
  console.log(`\nEXECUTION ID                                  WORKFLOW         STATUS      CREATED`);
  console.log('-'.repeat(90));
  for (const ex of executions) {
    console.log(`${ex.executionId.padEnd(44)} ${ex.workflowId.padEnd(16)} ${ex.status.padEnd(11)} ${ex.createdAt}`);
  }
  console.log();
}
