import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// --- Child workflow: PaymentFlow ---
const ChargeResult = z.object({ receiptId: z.string(), charged: z.number() });
const PaymentOutput = z.object({ receiptId: z.string(), success: z.boolean() });

const paymentFlow = nexum.workflow<{ amount: number; orderId: string }>('PaymentFlow')
  .effect('charge', ChargeResult, async (ctx) => {
    await new Promise(r => setTimeout(r, 200));
    console.log(`[NEXUM] (child) EFFECT charge: $${ctx.input.amount} for ${ctx.input.orderId}`);
    return { receiptId: `REC-${Date.now()}`, charged: ctx.input.amount };
  })
  .compute('finalize', PaymentOutput, (ctx) => {
    const charge = ctx.get('charge');
    console.log(`[NEXUM] (child) COMPUTE finalize: receipt=${charge.receiptId}`);
    return { receiptId: charge.receiptId, success: true };
  })
  .build();

// --- Parent workflow: OrderPipeline ---
const ValidationResult = z.object({ totalAmount: z.number(), valid: z.boolean() });
const ConfirmationResult = z.object({ sent: z.boolean(), receiptId: z.string() });

const orderPipeline = nexum.workflow<{ orderId: string }>('OrderPipeline')
  .effect('validate', ValidationResult, async (ctx) => {
    await new Promise(r => setTimeout(r, 100));
    console.log(`[NEXUM] EFFECT validate: order=${ctx.input.orderId}`);
    return { totalAmount: 4980, valid: true };
  })
  .subworkflow('process_payment', PaymentOutput, {
    workflow: paymentFlow,
    input: (ctx) => ({
      amount: ctx.get('validate').totalAmount,
      orderId: ctx.input.orderId,
    }),
  })
  .compute('send_confirmation', ConfirmationResult, (ctx) => {
    const payment = ctx.get('process_payment');
    console.log(`[DEMO] Sending confirmation for receipt: ${payment.receiptId}`);
    return { sent: true, receiptId: payment.receiptId };
  })
  .build();

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

async function runDemo() {
  const client = new NexumClient();

  // Worker handles BOTH workflows
  const worker = new Worker('localhost:50051', 'subworkflow-worker-1', 4);
  worker.register(orderPipeline);
  worker.register(paymentFlow);

  console.log('\n=== NEXUM SUBWORKFLOW DEMO ===\n');

  await worker.start();

  const executionId = await client.startExecution(
    orderPipeline.workflowId,
    orderPipeline.versionHash,
    { orderId: 'ORD-001' }
  );
  console.log(`[DEMO] Parent execution: ${executionId}`);

  // Poll for parent completion
  let finalStatus;
  for (let i = 0; i < 60; i++) {
    await sleep(1000);
    finalStatus = await client.getStatus(executionId);
    if (finalStatus.status === 'COMPLETED' || finalStatus.status === 'FAILED') break;
  }

  worker.stop();

  console.log('\n=== RESULT ===');
  console.log('Status:', finalStatus?.status);

  if (finalStatus?.status === 'COMPLETED') {
    const confirmation = finalStatus.completedNodes?.['send_confirmation'];
    if (confirmation) {
      console.log(`  Sent: ${confirmation.sent}`);
      console.log(`  Receipt: ${confirmation.receiptId}`);
    }
    console.log('\n[SUCCESS] Subworkflow pipeline completed!');
  } else {
    console.log('Completed nodes:', Object.keys(finalStatus?.completedNodes ?? {}));
    console.log('\n[FAILED] Pipeline did not complete.');
  }
}

runDemo().catch(console.error);
