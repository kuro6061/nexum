import { NexumClient } from 'nexum-js';

const workflowId = process.argv[3];
if (!workflowId) {
  console.error('Usage: nexum versions <workflow-id>');
  process.exit(1);
}

const client = new NexumClient();
const versions = await client.listWorkflowVersions(workflowId);

if (versions.length === 0) {
  console.log(`No versions found for "${workflowId}".`);
} else {
  console.log(`\nVersions for "${workflowId}":\n`);
  for (const v of versions) {
    const marker = v.activeExecutions > 0 ? ' <- ACTIVE' : '';
    console.log(`  ${v.versionHash.slice(0, 16)}... [${v.compatibility}] ${v.registeredAt}${marker}`);
    if (v.activeExecutions > 0) {
      console.log(`    ${v.activeExecutions} execution(s) in progress`);
    }
  }
}
