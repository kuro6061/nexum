import { NexumClient } from '@nexum/sdk';
import { parseArgs } from 'node:util';

const { values, positionals } = parseArgs({
  options: {
    approver: { type: 'string', default: 'cli-user' },
    reason: { type: 'string', default: 'Rejected' },
  },
  allowPositionals: true,
});

const executionId = positionals[1];
const nodeId = positionals[2];

if (!executionId || !nodeId) {
  console.error('Usage: nexum reject <execution-id> <node-id> [--approver "Bob"] [--reason "Too risky"]');
  process.exit(1);
}

const client = new NexumClient();
await client.rejectTask(executionId, nodeId, values.approver!, values.reason!);
console.log(`\u2717 Rejected: ${nodeId} in ${executionId}`);
