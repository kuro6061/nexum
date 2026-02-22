import { NexumClient } from 'nexum-js';

const client = new NexumClient();
const items = await client.getPendingApprovals();

if (items.length === 0) {
  console.log('No pending approvals.');
} else {
  console.log(`\nPending Approvals (${items.length}):\n`);
  for (const item of items) {
    console.log(`  ${item.workflowId} / ${item.nodeId}`);
    console.log(`    Execution: ${item.executionId}`);
    console.log(`    Since:     ${item.startedAt}`);
    console.log('');
  }
  console.log('Approve with: nexum approve <execution-id> <node-id> --approver "Name"');
}
