import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

const InvoiceData = z.object({
  invoice_id: z.string(),
  amount: z.number(),
  customer: z.string(),
});

const SendResult = z.object({
  sent: z.boolean(),
  invoice_id: z.string(),
  approved_by: z.string(),
});

const invoiceWorkflow = nexum.workflow<{ amount: number; customer: string }>('InvoiceWorkflow')
  .effect('prepare_invoice', InvoiceData, async (ctx) => {
    console.log('[WORKER] Preparing invoice...');
    await sleep(300);
    return {
      invoice_id: `INV-${Date.now()}`,
      amount: ctx.input.amount,
      customer: ctx.input.customer,
    };
  })
  .humanApproval('finance_approval')
  .effect('send_to_customer', SendResult, async (ctx) => {
    const invoice = ctx.get('prepare_invoice');
    const approval = ctx.get('finance_approval');
    console.log(`[WORKER] Sending invoice ${invoice.invoice_id} (approved by ${approval.approver})...`);
    await sleep(300);
    return {
      sent: true,
      invoice_id: invoice.invoice_id,
      approved_by: approval.approver,
    };
  })
  .build();

async function runDemo() {
  const client = new NexumClient();

  console.log('\n=== NEXUM HUMAN APPROVAL DEMO ===\n');

  // Start worker
  const worker = new Worker('localhost:50051', 'approval-worker-1');
  worker.register(invoiceWorkflow);
  await worker.start();

  // Start execution
  const executionId = await client.startExecution(
    invoiceWorkflow.workflowId,
    invoiceWorkflow.versionHash,
    { amount: 5000, customer: 'Acme Corp' }
  );
  console.log(`[NEXUM] Started execution: ${executionId}`);

  // Wait for prepare_invoice to complete and finance_approval to be pending
  console.log('[DEMO] Waiting for invoice preparation...');
  await sleep(3000);

  // Check status - should be RUNNING with prepare_invoice done
  let status = await client.getStatus(executionId);
  console.log(`[DEMO] Status: ${status.status}`);
  console.log(`[DEMO] Completed nodes: ${Object.keys(status.completedNodes).join(', ') || 'none'}`);

  // Check pending approvals
  const pending = await client.getPendingApprovals();
  console.log(`\n[DEMO] Pending approvals: ${pending.length}`);
  for (const p of pending) {
    console.log(`  - ${p.workflowId} / ${p.nodeId} (exec: ${p.executionId})`);
  }

  // Simulate approval
  console.log('\n[DEMO] Simulating manager approval...');
  await client.approveTask(executionId, 'finance_approval', 'Alice (CFO)', 'Amount within budget, approved.');
  console.log('[DEMO] Approval submitted!\n');

  // Wait for send_to_customer to complete
  let finalStatus;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    finalStatus = await client.getStatus(executionId);
    if (finalStatus.status === 'COMPLETED') break;
  }

  worker.stop();

  console.log('\n=== RESULT ===');
  console.log('Status:', finalStatus?.status);
  console.log('Completed nodes:', Object.keys(finalStatus?.completedNodes ?? {}));
  if (finalStatus?.completedNodes?.send_to_customer) {
    console.log('Send result:', finalStatus.completedNodes.send_to_customer);
  }
  console.log('\n[SUCCESS] Human approval workflow completed!');
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

runDemo().catch(console.error);
