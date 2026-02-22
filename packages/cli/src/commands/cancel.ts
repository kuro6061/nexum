import { NexumClient } from 'nexum-js';

const executionId = process.argv[3];
if (!executionId) {
  console.error('Usage: nexum cancel <execution-id>');
  process.exit(1);
}

const client = new NexumClient();
await client.cancelExecution(executionId);
console.log(`Cancelled: ${executionId}`);
