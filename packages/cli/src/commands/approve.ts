import { NexumClient } from '@nexum/sdk';
import { parseArgs } from 'node:util';

const { values, positionals } = parseArgs({
  options: {
    approver: { type: 'string', default: 'cli-user' },
    comment: { type: 'string', default: '' },
  },
  allowPositionals: true,
});

const executionId = positionals[1];
const nodeId = positionals[2];

if (!executionId || !nodeId) {
  console.error('Usage: nexum approve <execution-id> <node-id> [--approver "Alice"] [--comment "LGTM"]');
  process.exit(1);
}

const client = new NexumClient();
await client.approveTask(executionId, nodeId, values.approver!, values.comment!);
console.log(`\u2713 Approved: ${nodeId} in ${executionId}`);
