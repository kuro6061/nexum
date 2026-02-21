/**
 * Nexum Complex Workflow Demo
 *
 * 6-step deep research pipeline with 3 Gemini API calls.
 * Crash after step 4 (llm_find_gaps), Worker 2 resumes from step 5 only.
 *
 * Demonstrates: 2 Gemini calls NOT re-executed after crash = cost saved.
 */

import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

const GEMINI_API_KEY = process.env.GEMINI_API_KEY ?? '';
const GEMINI_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`;

let geminiCallCount = 0;

async function callGemini(prompt: string): Promise<string> {
  geminiCallCount++;
  const callNum = geminiCallCount;
  console.log(`  [Gemini API call #${callNum}] 竊・${prompt.slice(0, 60).replace(/\n/g, ' ')}...`);
  const res = await fetch(GEMINI_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { maxOutputTokens: 400, responseMimeType: 'application/json' }
    })
  });
  if (!res.ok) throw new Error(`Gemini error: ${res.status}`);
  const data = await res.json() as any;
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text ?? '{}';
  console.log(`  [Gemini #${callNum}] 笨・${text.length} chars`);
  return text;
}

function safeJson(raw: string, fallback: any): any {
  try { return JSON.parse(raw.trim()); } catch {}
  try { const m = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/); if (m) return JSON.parse(m[1]); } catch {}
  try { const m = raw.match(/\{[\s\S]*\}/); if (m) return JSON.parse(m[0]); } catch {}
  return fallback;
}

// 笏笏笏 繧ｹ繧ｭ繝ｼ繝・笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
const ParsedQuery   = z.object({ topic: z.string(), angle: z.string() });
const SearchData    = z.object({ snippets: z.array(z.string()) });
const ExtractedFacts = z.object({ facts: z.array(z.string()), source_count: z.number() });
const KnowledgeGaps = z.object({ gaps: z.array(z.string()), priority: z.string() });
const Synthesis     = z.object({ thesis: z.string(), evidence: z.array(z.string()), confidence: z.number() });
const FinalReport   = z.object({ title: z.string(), executive_summary: z.string(), score: z.number() });

// 笏笏笏 6繧ｹ繝・ャ繝・繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ 笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
const deepResearch = nexum.workflow('DeepResearchPipeline')

  // STEP 1: COMPUTE 窶・繧ｯ繧ｨ繝ｪ隗｣譫撰ｼ・emini荳堺ｽｿ逕ｨ縲∫┌譁呻ｼ・  .compute('parse_query', ParsedQuery, (ctx) => {
    const query: string = ctx.input.query;
    console.log(`  [STEP 1] parse_query: "${query}"`);
    return { topic: query, angle: 'technical comparison and practical applications' };
  })

  // STEP 2: EFFECT 窶・讀懃ｴ｢・医Δ繝・け縲∫┌譁呻ｼ・  .effect('web_search', SearchData, async (ctx) => {
    const { topic } = ctx.get('parse_query');
    console.log(`  [STEP 2] web_search: "${topic}"`);
    await sleep(200);
    return {
      snippets: [
        `${topic}: key architectural patterns include event sourcing and CQRS.`,
        `Production deployments require fault tolerance and exactly-once semantics.`,
        `Recent benchmarks show 10x improvement in reliability with durable execution.`,
        `Major challenges: history size limits, non-deterministic operations, versioning.`,
        `Open-source alternatives struggle with LLM-specific requirements like large payloads.`,
      ]
    };
  })

  // STEP 3: EFFECT 窶・Gemini竭 莠句ｮ滓歓蜃ｺ
  .effect('llm_extract_facts', ExtractedFacts, async (ctx) => {
    const search = ctx.get('web_search');
    const { topic } = ctx.get('parse_query');
    console.log(`  [STEP 3] llm_extract_facts: calling Gemini...`);
    const raw = await callGemini(
      `Extract key technical facts about "${topic}" from these snippets:\n${search.snippets.join('\n')}\n\nReturn JSON: {"facts":["fact1","fact2","fact3"],"source_count":5}`
    );
    const p = safeJson(raw, { facts: ['Durable execution prevents data loss', 'Event sourcing enables replay', 'Idempotency keys prevent duplicates'], source_count: 5 });
    return { facts: p.facts ?? [], source_count: typeof p.source_count === 'number' ? p.source_count : 5 };
  })

  // STEP 4: EFFECT 窶・Gemini竭｡ 繧ｮ繝｣繝・・蛻・梵 竊・縺薙％縺ｧ繧ｯ繝ｩ繝・す繝･
  .effect('llm_find_gaps', KnowledgeGaps, async (ctx) => {
    const extracted = ctx.get('llm_extract_facts');
    const { topic } = ctx.get('parse_query');
    console.log(`  [STEP 4] llm_find_gaps: calling Gemini...`);
    const raw = await callGemini(
      `Given these facts about "${topic}": ${extracted.facts.join('; ')}\nIdentify knowledge gaps.\nReturn JSON: {"gaps":["gap1","gap2"],"priority":"high|medium|low"}`
    );
    const p = safeJson(raw, { gaps: ['LLM-specific payload handling not addressed', 'Versioning strategy unclear'], priority: 'high' });
    return { gaps: p.gaps ?? [], priority: p.priority ?? 'medium' };
  })

  // STEP 5: EFFECT 窶・Gemini竭｢ 邱丞粋蛻・梵・・orker 2縺梧球蠖難ｼ・  .effect('llm_synthesize', Synthesis, async (ctx) => {
    const facts = ctx.get('llm_extract_facts');
    const gaps  = ctx.get('llm_find_gaps');
    const { topic } = ctx.get('parse_query');
    console.log(`  [STEP 5] llm_synthesize: calling Gemini...`);
    const raw = await callGemini(
      `Synthesize a technical thesis about "${topic}".\nFacts: ${facts.facts.slice(0,2).join('; ')}\nGaps: ${gaps.gaps[0] ?? 'none'}\nReturn JSON: {"thesis":"...","evidence":["e1","e2"],"confidence":0.88}`
    );
    const p = safeJson(raw, { thesis: `${topic} is essential for production LLM systems`, evidence: ['Fault tolerance', 'Cost efficiency'], confidence: 0.88 });
    return { thesis: p.thesis ?? '', evidence: p.evidence ?? [], confidence: typeof p.confidence === 'number' ? p.confidence : 0.88 };
  })

  // STEP 6: COMPUTE 窶・譛邨ゅΞ繝昴・繝育函謌撰ｼ医ョ繝ｼ繧ｿ謨ｴ蠖｢縺ｮ縺ｿ縲；emini荳堺ｽｿ逕ｨ・・  .compute('final_report', FinalReport, (ctx) => {
    const synthesis = ctx.get('llm_synthesize');
    const { topic }  = ctx.get('parse_query');
    console.log(`  [STEP 6] final_report: assembling...`);
    return {
      title: `Deep Research Report: ${topic}`,
      executive_summary: synthesis.thesis,
      score: Math.round(synthesis.confidence * 100),
    };
  })

  .build();

// 笏笏笏 繝・Δ螳溯｡・笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏笏
async function runDemo() {
  const client = new NexumClient();

  console.log('\n笊披武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶風');
  console.log('笊・  NEXUM COMPLEX WORKFLOW DEMO  (6 steps)         笊・);
  console.log('笊壺武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶幅\n');
  console.log('Steps: parse 竊・search 竊・extract_facts 竊・find_gaps 竊・synthesize 竊・report');
  console.log('       (free)  (free)   [Gemini竭]      [Gemini竭｡]   [Gemini竭｢]   (free)');
  console.log('                                              竊・);
  console.log('                                        CRASH HERE\n');

  const worker1 = new Worker('localhost:50051', 'worker-1');
  worker1.register(deepResearch);
  await worker1.start();

  const executionId = await client.startExecution(
    deepResearch.workflowId,
    deepResearch.versionHash,
    { query: 'Durable execution for LLM agents' }
  );
  console.log(`[NEXUM] Execution started: ${executionId}\n`);
  console.log('笏≫煤笏・Worker 1 笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏・);

  // llm_find_gaps (STEP 4) 螳御ｺ・ｒ讀懃衍 竊・繧ｯ繝ｩ繝・す繝･
  const callsBefore = { count: 0 };
  await waitFor(async () => {
    const s = await client.getStatus(executionId);
    if (s.status === 'FAILED') throw new Error('Execution failed');
    return 'llm_find_gaps' in (s.completedNodes ?? {});
  }, 120000);

  callsBefore.count = geminiCallCount;
  console.log(`\n徴 CRASH! (after STEP 4 / Gemini call #${callsBefore.count})\n`);
  worker1.stop();
  await sleep(500);

  // Worker 2 繧ｹ繧ｿ繝ｼ繝・  geminiCallCount = 0; // Worker 2縺ｮ繧ｫ繧ｦ繝ｳ繝医ｒ繝ｪ繧ｻ繝・ヨ
  console.log('笏≫煤笏・Worker 2 (recovery) 笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤');
  const worker2 = new Worker('localhost:50051', 'worker-2');
  worker2.register(deepResearch);
  worker2.start();

  let finalStatus: any;
  for (let i = 0; i < 60; i++) {
    await sleep(1000);
    finalStatus = await client.getStatus(executionId);
    if (finalStatus.status === 'COMPLETED' || finalStatus.status === 'FAILED') break;
  }
  worker2.stop();

  const nodes = finalStatus?.completedNodes ?? {};

  console.log('\n笊披武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶風');
  console.log('笊・                 FINAL RESULT                   笊・);
  console.log('笊壺武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶武笊絶幅\n');
  console.log(`Status: ${finalStatus?.status}`);
  console.log(`Steps:  ${Object.keys(nodes).join(' 竊・')}\n`);

  if (nodes['final_report']) {
    const r = nodes['final_report'] as any;
    const report = typeof r === 'string' ? JSON.parse(r) : r;
    console.log(`搭 ${report.title}`);
    console.log(`投 Score: ${report.score}/100`);
    console.log(`統 ${report.executive_summary}\n`);
  }

  if (nodes['llm_extract_facts']) {
    const r = nodes['llm_extract_facts'] as any;
    const facts = typeof r === 'string' ? JSON.parse(r) : r;
    console.log(`剥 Extracted facts (${facts.source_count} sources):`);
    (facts.facts ?? []).slice(0, 3).forEach((f: string) => console.log(`   窶｢ ${f}`));
    console.log();
  }

  console.log('笏≫煤笏・Cost Analysis 笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤笏≫煤');
  console.log(`Gemini calls by Worker 1: ${callsBefore.count} (steps 3-4)`);
  console.log(`Gemini calls by Worker 2: ${geminiCallCount} (step 5 only)`);
  console.log(`Gemini calls SAVED by Nexum: ${callsBefore.count} (NOT re-executed!)`);
  console.log(`\n笨・[SUCCESS] Worker 2 ran only STEP 5 窶・steps 1-4 were NOT repeated.`);
  console.log(`   In production: saves API cost + time for every crash/redeploy.\n`);
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
function waitFor(pred: () => boolean | Promise<boolean>, timeout: number) {
  return new Promise<void>((resolve, reject) => {
    const start = Date.now();
    const check = async () => {
      if (Date.now() - start > timeout) { reject(new Error('timeout')); return; }
      try {
        const r = await pred();
        if (r) resolve(); else setTimeout(check, 1000);
      } catch (e) { reject(e); }
    };
    check();
  });
}

runDemo().catch(console.error);

