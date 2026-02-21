import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

const PaperAnalysis = z.object({
  title: z.string(),
  score: z.number(),
  summary: z.string(),
});

const BatchSummary = z.object({
  totalPapers: z.number(),
  avgScore: z.number(),
  topPaper: z.string(),
  combined: z.string(),
});

const researchBatch = nexum.workflow<{ papers: string[] }>('ResearchBatch')
  .map('analyze', PaperAnalysis, {
    items: (ctx) => ctx.input.papers,
    handler: async (_ctx, paper: string, index: number) => {
      // Simulate LLM analysis (mock)
      await new Promise(r => setTimeout(r, 100 + Math.random() * 200));
      return {
        title: paper,
        score: Math.round(70 + Math.random() * 30),
        summary: `Analysis of paper ${index + 1}: ${paper.substring(0, 30)}...`,
      };
    },
  })
  .reduce('summarize', BatchSummary, (ctx) => {
    const results = ctx.getMapResults('analyze');
    const avgScore = results.reduce((s: number, r: any) => s + r.score, 0) / results.length;
    const top = results.sort((a: any, b: any) => b.score - a.score)[0];
    return {
      totalPapers: results.length,
      avgScore: Math.round(avgScore),
      topPaper: top.title,
      combined: results.map((r: any) => r.summary).join('\n'),
    };
  })
  .build();

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

async function runDemo() {
  const client = new NexumClient();

  const worker = new Worker('localhost:50051', 'map-worker-1', 5);
  worker.register(researchBatch);

  console.log('\n=== NEXUM MAP/REDUCE DEMO ===\n');

  await worker.start();

  const papers = [
    'Attention Is All You Need',
    'BERT: Pre-training of Deep Bidirectional Transformers',
    'GPT-4 Technical Report',
    'Constitutional AI: Harmlessness from AI Feedback',
    'Scaling Laws for Neural Language Models',
  ];

  console.log(`Starting batch analysis of ${papers.length} papers in parallel...`);
  const executionId = await client.startExecution(
    researchBatch.workflowId,
    researchBatch.versionHash,
    { papers }
  );
  console.log(`[NEXUM] Started execution: ${executionId}`);

  // Poll for completion
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
    const summary = finalStatus.completedNodes?.['summarize'];
    if (summary) {
      console.log(`  Total papers: ${summary.totalPapers}`);
      console.log(`  Avg score: ${summary.avgScore}`);
      console.log(`  Top paper: ${summary.topPaper}`);
    }
    console.log('\n[SUCCESS] MAP/REDUCE pipeline completed!');
  } else {
    console.log('Completed nodes:', Object.keys(finalStatus?.completedNodes ?? {}));
    console.log('\n[FAILED] Pipeline did not complete.');
  }
}

runDemo().catch(console.error);
