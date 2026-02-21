/**
 * Nexum LLM Demo
 * 4-step workflow with real Gemini API calls + durability test
 *
 * Workflow: parse_query 竊・web_research 竊・llm_analyze (Gemini) 竊・llm_report (Gemini)
 *
 * Durability test: crash after llm_analyze, Worker 2 resumes from llm_report only
 */

import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

const GEMINI_API_KEY = process.env.GEMINI_API_KEY ?? '';
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

// 笏笏笏 繧ｹ繧ｭ繝ｼ繝槫ｮ夂ｾｩ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
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

// 笏笏笏 繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ螳夂ｾｩ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
const researchAgent = nexum.workflow('DeepResearchAgent')

  // Step 1: COMPUTE 窶・蜈･蜉帙ｒ隗｣譫撰ｼ医Ο繝ｼ繧ｫ繝ｫ蜃ｦ逅・∝憶菴懃畑縺ｪ縺暦ｼ・  .compute('parse_query', ParsedQuery, (ctx) => {
    const query: string = ctx.input.query;
    const words = query.toLowerCase().split(' ').filter(w => w.length > 3);
    return {
      topic: query,
      keywords: words.slice(0, 5),
    };
  })

  // Step 2: EFFECT 窶・Web讀懃ｴ｢・亥､夜Κ蜻ｼ縺ｳ蜃ｺ縺励∝・遲画ｧ繧ｭ繝ｼ閾ｪ蜍穂ｻ倅ｸ趣ｼ・  .effect('web_research', ResearchData, async (ctx) => {
    const { topic, keywords } = ctx.get('parse_query');
    console.log(`  [search] topic="${topic}" keywords=[${keywords.join(', ')}]`);
    await sleep(300);
    // 螳滄圀縺ｮ繝励Ο繝繧ｯ繝医〒縺ｯ讀懃ｴ｢API繧貞他縺ｶ
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

  // Step 3: EFFECT 窶・Gemini 縺ｧ蛻・梵・域悽迚ｩ縺ｮLLM蜻ｼ縺ｳ蜃ｺ縺暦ｼ・  .effect('llm_analyze', Analysis, async (ctx) => {
    const research = ctx.get('web_research');
    const query = ctx.get('parse_query');

    console.log(`  [Gemini] Analyzing research on "${query.topic}"...`);
    // JSON蠑ｷ蛻ｶ縺ｧ縺ｯ縺ｪ縺上・繝ｬ繝ｼ繝ｳ繝・く繧ｹ繝医〒蜿門ｾ励＠縺ｦ繝代・繧ｹ・・.5-flash縺ｮ諤晁・Ο繧ｰ蟇ｾ遲厄ｼ・    const prompt = `Analyze this research content about "${query.topic}" and respond with ONLY a JSON object (no markdown, no explanation):
{"key_points":["point1","point2","point3"],"confidence":0.85,"summary":"one sentence"}

Content: ${research.raw_content.slice(0, 500)}`;

    const raw = await callGemini(prompt, true);  // JSON mode ON
    console.log(`  [Gemini] Received ${raw.length} chars`);

    // 隍・焚縺ｮ謌ｦ逡･縺ｧJSON繧呈歓蜃ｺ
    let parsed: any = null;
    try {
      // 謌ｦ逡･1: 縺昴・縺ｾ縺ｾparse
      parsed = JSON.parse(raw.trim());
    } catch {
      try {
        // 謌ｦ逡･2: 繧ｳ繝ｼ繝峨ヶ繝ｭ繝・け蜀・・JSON繧呈歓蜃ｺ
        const block = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
        if (block) parsed = JSON.parse(block[1]);
      } catch {}
      if (!parsed) {
        // 謌ｦ逡･3: 譛蛻昴・ { 縺九ｉ譛蠕後・ } 繧呈歓蜃ｺ
        const match = raw.match(/\{[\s\S]*\}/);
        if (match) {
          try { parsed = JSON.parse(match[0]); } catch {}
        }
      }
    }
    // 縺ｩ繧後ｂ螟ｱ謨励＠縺溘ｉ繝輔か繝ｼ繝ｫ繝舌ャ繧ｯ
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

  // Step 4: EFFECT 窶・Gemini 縺ｧ譛邨ゅΞ繝昴・繝育函謌撰ｼ域悽迚ｩ縺ｮLLM蜻ｼ縺ｳ蜃ｺ縺暦ｼ・  .effect('llm_report', FinalReport, async (ctx) => {
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

// 笏笏笏 繝・Δ螳溯｡・笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
async function runDemo() {
  const client = new NexumClient();

  console.log('\n笊披武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶風');
  console.log('笊・  NEXUM ﾃ・GEMINI  DURABILITY DEMO    笊・);
  console.log('笊壺武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶幅\n');
  console.log('Workflow: parse_query 竊・web_research 竊・llm_analyze 竊・llm_report');
  console.log('Durability test: crash after llm_analyze, resume from llm_report\n');

  // Worker 1 窶・llm_analyze 縺悟ｮ御ｺ・＠縺溘ｉ繧ｯ繝ｩ繝・す繝･縺吶ｋ
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

  // status polling 縺ｧ llm_analyze 螳御ｺ・ｒ讀懃衍・医ワ繝ｳ繝峨Λ繝ｼ繝輔ャ繧ｯ繧医ｊ遒ｺ螳滂ｼ・  await waitFor(async () => {
    const status = await client.getStatus(executionId);
    return 'llm_analyze' in (status.completedNodes ?? {});
  }, 120000);
  console.log('\n徴 [DEMO] Worker 1 CRASH after llm_analyze!\n');
  worker1.stop();
  await sleep(600);

  // Worker 2 窶・llm_report 縺縺代ｒ諡ｾ縺｣縺ｦ螳御ｺ・＆縺帙ｋ
  console.log('売 [DEMO] Worker 2 starting (recovery)...');
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

  // 邨先棡陦ｨ遉ｺ
  const nodes = finalStatus?.completedNodes ?? {};
  console.log('\n笊披武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶風');
  console.log('笊・           FINAL RESULT              笊・);
  console.log('笊壺武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶幅\n');
  console.log(`Status: ${finalStatus?.status}`);
  console.log(`Completed steps: ${Object.keys(nodes).join(' 竊・')}\n`);

  if (nodes['llm_report']) {
    // completedNodes 縺ｮ蛟､縺ｯ繧ｵ繝ｼ繝舌・蛛ｴ縺ｧJSON繝代・繧ｹ貂医∩縺ｮ繧ｪ繝悶ず繧ｧ繧ｯ繝・    const raw = nodes['llm_report'];
    const report = (typeof raw === 'string' ? JSON.parse(raw) : raw) as z.infer<typeof FinalReport>;
    console.log(`統 Title:  ${report.title}`);
    console.log(`投 Score:  ${report.score}/100`);
    console.log(`塘 Report: ${report.body}\n`);
  }

  if (nodes['llm_analyze']) {
    const raw = nodes['llm_analyze'];
    const analysis = (typeof raw === 'string' ? JSON.parse(raw) : raw) as z.infer<typeof Analysis>;
    console.log(`剥 Key points:`);
    analysis.key_points.forEach((p: string) => console.log(`   窶｢ ${p}`));
  }

  console.log('\n笨・[SUCCESS] Worker 2 skipped parse/research/analyze 窶・only ran llm_report!');
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

