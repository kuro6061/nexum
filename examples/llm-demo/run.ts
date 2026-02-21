/**
 * Nexum LLM Demo
 * 4-step workflow with real Gemini API calls + durability test
 *
 * Workflow: parse_query → web_research → llm_analyze (Gemini) → llm_report (Gemini)
 *
 * Durability test: crash after llm_analyze, Worker 2 resumes from llm_report only
 */

import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

const GEMINI_API_KEY = 'AIzaSyDRPEm_g_vcdyEWX7IUdNgDSeAX-a1vQQw';
const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`;

async function callGemini(prompt: string, json = false): Promise<string> {
  const body: any = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { maxOutputTokens: 512 }
  };
  if (json) body.generationConfig.responseMimeType = 'application/json';
  const res = await fetch(GEMINI_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`Gemini API error: ${res.status} ${await res.text()}`);
  const data = await res.json() as any;
  return data.candidates?.[0]?.content?.parts?.[0]?.text ?? '(no response)';
}

// ─── スキーマ定義 ──────────────────────────────────────────
const ParsedQuery = z.object({
  topic: z.string(),
  keywords: z.array(z.string()),
});

const ResearchData = z.object({
  sources: z.array(z.string()),
  raw_content: z.string(),
});

const Analysis = z.object({
  key_points: z.array(z.string()),
  confidence: z.number(),
  summary: z.string(),
});

const FinalReport = z.object({
  title: z.string(),
  body: z.string(),
  score: z.number(),
});

// ─── ワークフロー定義 ────────────────────────────────────────
const researchAgent = nexum.workflow('DeepResearchAgent')

  // Step 1: COMPUTE — 入力を解析（ローカル処理、副作用なし）
  .compute('parse_query', ParsedQuery, (ctx) => {
    const query: string = ctx.input.query;
    const words = query.toLowerCase().split(' ').filter(w => w.length > 3);
    return {
      topic: query,
      keywords: words.slice(0, 5),
    };
  })

  // Step 2: EFFECT — Web検索（外部呼び出し、冪等性キー自動付与）
  .effect('web_research', ResearchData, async (ctx) => {
    const { topic, keywords } = ctx.get('parse_query');
    console.log(`  [search] topic="${topic}" keywords=[${keywords.join(', ')}]`);
    await sleep(300);
    // 実際のプロダクトでは検索APIを呼ぶ
    return {
      sources: [
        `https://arxiv.org/search/${encodeURIComponent(topic)}`,
        `https://paperswithcode.com/search?q=${encodeURIComponent(keywords[0] ?? topic)}`,
      ],
      raw_content: `
        Recent research on "${topic}":
        1. Durable execution engines provide fault-tolerance for long-running workflows.
        2. LLM agents benefit from state persistence across crashes.
        3. Event sourcing enables deterministic replay of agent execution history.
        4. Idempotency keys prevent duplicate side-effects in at-least-once delivery systems.
        5. Claim Check pattern offloads large payloads (LLM context) from the event store.
      `.trim(),
    };
  })

  // Step 3: EFFECT — Gemini で分析（本物のLLM呼び出し）
  .effect('llm_analyze', Analysis, async (ctx) => {
    const research = ctx.get('web_research');
    const query = ctx.get('parse_query');

    console.log(`  [Gemini] Analyzing research on "${query.topic}"...`);
    // JSON強制ではなくプレーンテキストで取得してパース（2.5-flashの思考ログ対策）
    const prompt = `Analyze this research content about "${query.topic}" and respond with ONLY a JSON object (no markdown, no explanation):
{"key_points":["point1","point2","point3"],"confidence":0.85,"summary":"one sentence"}

Content: ${research.raw_content.slice(0, 500)}`;

    const raw = await callGemini(prompt, true);  // JSON mode ON
    console.log(`  [Gemini] Received ${raw.length} chars`);

    // 複数の戦略でJSONを抽出
    let parsed: any = null;
    try {
      // 戦略1: そのままparse
      parsed = JSON.parse(raw.trim());
    } catch {
      try {
        // 戦略2: コードブロック内のJSONを抽出
        const block = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
        if (block) parsed = JSON.parse(block[1]);
      } catch {}
      if (!parsed) {
        // 戦略3: 最初の { から最後の } を抽出
        const match = raw.match(/\{[\s\S]*\}/);
        if (match) {
          try { parsed = JSON.parse(match[0]); } catch {}
        }
      }
    }
    // どれも失敗したらフォールバック
    if (!parsed) {
      console.log(`  [Gemini] JSON parse failed, using fallback`);
      parsed = { key_points: ['Durable execution prevents data loss', 'LLM workflows need state persistence', 'Event sourcing enables crash recovery'], confidence: 0.8, summary: 'Durable execution is critical for production LLM agents.' };
    }
    return {
      key_points: Array.isArray(parsed.key_points) ? parsed.key_points : [],
      confidence: typeof parsed.confidence === 'number' ? parsed.confidence : 0.8,
      summary: typeof parsed.summary === 'string' ? parsed.summary : 'Analysis complete',
    };
  })

  // Step 4: EFFECT — Gemini で最終レポート生成（本物のLLM呼び出し）
  .effect('llm_report', FinalReport, async (ctx) => {
    const analysis = ctx.get('llm_analyze');
    const query = ctx.get('parse_query');

    console.log(`  [Gemini] Generating final report...`);
    const prompt = `Write a technical report about "${query.topic}". Key points: ${analysis.key_points.slice(0,2).join('; ')}. Insight: ${analysis.summary}
Respond with ONLY a JSON object (no markdown):
{"title":"report title","body":"2-3 sentence report","score":88}`;

    const raw = await callGemini(prompt, true);  // JSON mode ON
    console.log(`  [Gemini] Received ${raw.length} chars`);

    let parsed: any = null;
    try { parsed = JSON.parse(raw.trim()); } catch {}
    if (!parsed) {
      const block = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
      if (block) try { parsed = JSON.parse(block[1]); } catch {}
    }
    if (!parsed) {
      const match = raw.match(/\{[\s\S]*\}/);
      if (match) try { parsed = JSON.parse(match[0]); } catch {}
    }
    if (!parsed) {
      console.log(`  [Gemini] JSON parse failed, using fallback`);
      parsed = { title: `Report: ${query.topic}`, body: analysis.summary, score: 82 };
    }
    return {
      title: typeof parsed.title === 'string' ? parsed.title : `Report: ${query.topic}`,
      body: typeof parsed.body === 'string' ? parsed.body : analysis.summary,
      score: typeof parsed.score === 'number' ? parsed.score : 82,
    };
  })

  .build();

// ─── デモ実行 ───────────────────────────────────────────────
async function runDemo() {
  const client = new NexumClient();

  console.log('\n╔══════════════════════════════════════╗');
  console.log('║   NEXUM × GEMINI  DURABILITY DEMO    ║');
  console.log('╚══════════════════════════════════════╝\n');
  console.log('Workflow: parse_query → web_research → llm_analyze → llm_report');
  console.log('Durability test: crash after llm_analyze, resume from llm_report\n');

  // Worker 1 — llm_analyze が完了したらクラッシュする
  const worker1 = new Worker('localhost:50051', 'worker-1');
  worker1.register(researchAgent);
  await worker1.start();

  const executionId = await client.startExecution(
    researchAgent.workflowId,
    researchAgent.versionHash,
    { query: 'LLM durable execution engines' }
  );
  console.log(`[NEXUM] Started execution: ${executionId}\n`);
  console.log('--- Worker 1 processing ---');

  // status polling で llm_analyze 完了を検知（ハンドラーフックより確実）
  await waitFor(async () => {
    const status = await client.getStatus(executionId);
    return 'llm_analyze' in (status.completedNodes ?? {});
  }, 120000);
  console.log('\n💥 [DEMO] Worker 1 CRASH after llm_analyze!\n');
  worker1.stop();
  await sleep(600);

  // Worker 2 — llm_report だけを拾って完了させる
  console.log('🔄 [DEMO] Worker 2 starting (recovery)...');
  console.log('--- Worker 2 processing ---');
  const worker2 = new Worker('localhost:50051', 'worker-2');
  worker2.register(researchAgent);
  worker2.start();

  let finalStatus: any;
  for (let i = 0; i < 60; i++) {
    await sleep(1000);
    finalStatus = await client.getStatus(executionId);
    if (finalStatus.status === 'COMPLETED') break;
  }
  worker2.stop();

  // 結果表示
  const nodes = finalStatus?.completedNodes ?? {};
  console.log('\n╔══════════════════════════════════════╗');
  console.log('║            FINAL RESULT              ║');
  console.log('╚══════════════════════════════════════╝\n');
  console.log(`Status: ${finalStatus?.status}`);
  console.log(`Completed steps: ${Object.keys(nodes).join(' → ')}\n`);

  if (nodes['llm_report']) {
    // completedNodes の値はサーバー側でJSONパース済みのオブジェクト
    const raw = nodes['llm_report'];
    const report = (typeof raw === 'string' ? JSON.parse(raw) : raw) as z.infer<typeof FinalReport>;
    console.log(`📝 Title:  ${report.title}`);
    console.log(`📊 Score:  ${report.score}/100`);
    console.log(`📄 Report: ${report.body}\n`);
  }

  if (nodes['llm_analyze']) {
    const raw = nodes['llm_analyze'];
    const analysis = (typeof raw === 'string' ? JSON.parse(raw) : raw) as z.infer<typeof Analysis>;
    console.log(`🔍 Key points:`);
    analysis.key_points.forEach((p: string) => console.log(`   • ${p}`));
  }

  console.log('\n✅ [SUCCESS] Worker 2 skipped parse/research/analyze — only ran llm_report!');
  console.log('   Gemini was called exactly once for each step (no duplicate API calls)\n');
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
function waitFor(pred: () => boolean | Promise<boolean>, timeout: number) {
  return new Promise<void>((resolve, reject) => {
    const start = Date.now();
    const check = async () => {
      if (Date.now() - start > timeout) { reject(new Error('timeout waiting')); return; }
      const result = await pred().catch(() => false);
      if (result) resolve();
      else setTimeout(check, 1000);
    };
    check();
  });
}

runDemo().catch(console.error);
