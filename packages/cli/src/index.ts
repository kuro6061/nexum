#!/usr/bin/env node
import { parseArgs } from 'node:util';

const { positionals } = parseArgs({ allowPositionals: true });
const command = positionals[0];

switch (command) {
  case 'dev':       await import('./commands/dev.js');       break;
  case 'ps':        await import('./commands/ps.js');        break;
  case 'cancel':    await import('./commands/cancel.js');    break;
  case 'versions':  await import('./commands/versions.js');  break;
  case 'approve':   await import('./commands/approve.js');   break;
  case 'reject':    await import('./commands/reject.js');    break;
  case 'approvals': await import('./commands/approvals.js'); break;
  case 'diff':      await import('./commands/diff.js');      break;
  default:
    console.log(`nexum <command>

Commands:
  dev        Start local Nexum server (auto-finds nexum-server binary)
  ps         List executions  [--workflow] [--status] [--limit]
  cancel     Cancel an execution  <execution-id>
  versions   List registered workflow versions  <workflow-id>
  approve    Approve a pending task  <execution-id> <node-id> [--approver] [--comment]
  reject     Reject a pending task   <execution-id> <node-id> [--approver] [--reason]
  approvals  List pending human approvals
  diff       Compare latest two workflow versions  <workflow-id> [--json]

Examples:
  nexum dev
  nexum ps --status RUNNING
  nexum ps --workflow ResearchAgent
  nexum cancel exec-abc123
  nexum versions ResearchAgent
  nexum approvals
  nexum approve exec-abc123 finance_approval --approver "Alice"
  nexum diff ResearchAgent --json
`);
}
