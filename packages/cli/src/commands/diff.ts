import { NexumClient } from 'nexum-sdk';
import { parseArgs } from 'node:util';

const { values, positionals } = parseArgs({
  options: {
    json: { type: 'boolean', default: false },
  },
  allowPositionals: true,
});

const workflowId = positionals[1];
if (!workflowId) {
  console.error('Usage: nexum diff <workflow-id> [--json]');
  process.exit(1);
}

const client = new NexumClient();
const versions = await client.listWorkflowVersions(workflowId);

if (versions.length < 2) {
  console.log('Only one version registered. Nothing to diff.');
  process.exit(0);
}

const latest = versions[0];
const previous = versions[1];

const diffResult = {
  workflow_id: workflowId,
  base_version: previous.versionHash.slice(0, 16) + '...',
  target_version: latest.versionHash.slice(0, 16) + '...',
  compatibility_level: latest.compatibility,
  recommended_action: latest.compatibility === 'BREAKING'
    ? 'parallel_active_versions'
    : latest.compatibility === 'SAFE'
    ? 'rolling_upgrade'
    : 'no_action',
  exit_code: latest.compatibility === 'BREAKING' ? 1 : 0,
  active_executions_on_old_version: previous.activeExecutions,
};

if (values.json) {
  console.log(JSON.stringify(diffResult, null, 2));
} else {
  console.log(`\nWorkflow: ${workflowId}`);
  console.log(`Base:   ${diffResult.base_version}`);
  console.log(`Target: ${diffResult.target_version}`);
  console.log(`\nCompatibility: ${diffResult.compatibility_level}`);
  console.log(`Action:        ${diffResult.recommended_action}`);
  if (previous.activeExecutions > 0) {
    console.log(`\n\u26A0\uFE0F  ${previous.activeExecutions} execution(s) still running on old version`);
  }
  if (latest.compatibility === 'BREAKING') {
    console.log('\n[BREAKING] Old and new workers must run in parallel until old executions complete.');
  } else if (latest.compatibility === 'SAFE') {
    console.log('\n[SAFE] New nodes added only. Rolling upgrade is safe.');
  }
}

process.exit(diffResult.exit_code);
