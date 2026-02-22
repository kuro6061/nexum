# Nexum vs Temporal: 繧ｳ繝ｼ繝蛾㍼豈碑ｼ・
蜷後§繝ｦ繝ｼ繧ｹ繧ｱ繝ｼ繧ｹ・壹茎earch 竊・summarize 縺ｮ2繧ｹ繝・ャ繝励お繝ｼ繧ｸ繧ｧ繝ｳ繝・+ Worker繧ｯ繝ｩ繝・す繝･閠先ｧ縲・
---

## Nexum迚茨ｼ亥ｮ滄圀縺ｫ蜍輔＞縺溘さ繝ｼ繝会ｼ・
**繝輔ぃ繧､繝ｫ謨ｰ: 1繝輔ぃ繧､繝ｫ / 蜷郁ｨ・ 62陦・*

```typescript
// examples/core/demo/run.ts 窶・縺薙ｌ縺縺・import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// 竭 繧ｹ繧ｭ繝ｼ繝槫ｮ夂ｾｩ・・陦鯉ｼ・const SearchResult = z.object({ content: z.string() });
const Summary = z.object({ score: z.number(), text: z.string() });

// 竭｡ 繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ螳夂ｾｩ・・0陦鯉ｼ・const researchWorkflow = nexum.workflow('ResearchAgent')
  .effect('search', SearchResult, async (ctx) => {
    return { content: 'Research about: ' + ctx.input.query };
  })
  .effect('summarize', Summary, async (ctx) => {
    return { score: 88, text: 'Summary of: ' + ctx.get('search').content };
    //                                                    ^^^^^^^^^^^^
    //                                              蝙句ｮ牙・縺ｫ蜑阪せ繝・ャ繝励・邨先棡繧貞叙蠕・  })
  .build();

// 竭｢ 螳溯｡鯉ｼ・orker襍ｷ蜍・+ 螳溯｡碁幕蟋具ｼ会ｼ・0陦鯉ｼ・const worker1 = new Worker('localhost:50051', 'worker-1');
worker1.register(researchWorkflow);
await worker1.start();
const executionId = await client.startExecution(...);

// 竭｣ 繧ｯ繝ｩ繝・す繝･ & 蠕ｩ譌ｧ・・陦鯉ｼ・worker1.stop(); // 繧ｯ繝ｩ繝・す繝･謫ｬ莨ｼ
const worker2 = new Worker('localhost:50051', 'worker-2');
worker2.register(researchWorkflow);
worker2.start(); // 竊・閾ｪ蜍慕噪縺ｫ summarize 縺九ｉ蜀埼幕
```

---

## Temporal迚茨ｼ亥酔遲峨・縺薙→繧偵ｄ繧九さ繝ｼ繝会ｼ・
**繝輔ぃ繧､繝ｫ謨ｰ: 4繝輔ぃ繧､繝ｫ / 蜷郁ｨ・ 115陦・+ 險ｭ螳壹ヵ繧｡繧､繝ｫ**

```typescript
// === 繝輔ぃ繧､繝ｫ1: activities.ts・・0陦鯉ｼ・==
// Temporal縺ｯ繧｢繧ｯ繝・ぅ繝薙ユ繧｣縺ｨ繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ繧貞ｿ・★蛻・屬縺吶ｋ蠢・ｦ√′縺ゅｋ
import { ActivityCancellationType } from '@temporalio/activity';

export async function search(query: string): Promise<{ content: string }> {
  // 繧｢繧ｯ繝・ぅ繝薙ユ繧｣縺ｯ繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ縺ｨ蛻･繝輔ぃ繧､繝ｫ縺ｫ譖ｸ縺九↑縺・→縺・￠縺ｪ縺・宛邏・  return { content: 'Research about: ' + query };
}

export async function summarize(content: string): Promise<{ score: number; text: string }> {
  return { score: 88, text: 'Summary of: ' + content };
}
// 竊・ctx.get() 縺ｮ繧医≧縺ｪ蝙区耳隲悶・縺ｪ縺・ょｼ墓焚繧呈焔蜍輔〒貂｡縺吝ｿ・ｦ√′縺ゅｋ


// === 繝輔ぃ繧､繝ｫ2: workflows.ts・・8陦鯉ｼ・==
import { proxyActivities } from '@temporalio/workflow';
import type * as activities from './activities';

// 繧｢繧ｯ繝・ぅ繝薙ユ繧｣繧偵後・繝ｭ繧ｭ繧ｷ縲咲ｵ檎罰縺ｧ蜻ｼ縺ｶ・医Λ繝・ヱ繝ｼ縺悟ｿ・ｦ・ｼ・const { search, summarize } = proxyActivities<typeof activities>({
  startToCloseTimeout: '1 minute',
  retry: { maximumAttempts: 3 },
});

export async function researchWorkflow(query: string) {
  const searchResult = await search(query);      // 竊・蝙・ { content: string }
  const summary = await summarize(searchResult.content); // 竊・謇句虚縺ｧ繝・・繧ｿ繧堤ｹ九＄
  return summary;
}
// 竊・縺薙ｌ縺ｧ濶ｯ縺・′縲´LM縺ｮ蜃ｺ蜉幢ｼ域焚MB・峨ｒ縺昴・縺ｾ縺ｾ霑斐☆縺ｨ
//   Temporal縺ｮ History Size Limit・・0MB・峨↓蠑輔▲縺九°繧句庄閭ｽ諤ｧ縺後≠繧・

// === 繝輔ぃ繧､繝ｫ3: worker.ts・・0陦鯉ｼ・==
import { Worker } from '@temporalio/worker';
import * as activities from './activities';

async function run() {
  const worker = await Worker.create({
    workflowsPath: require.resolve('./workflows'),
    activities,
    taskQueue: 'research-queue',
    // 竊・bundler險ｭ螳壹′蠢・ｦ・ｼ・ebpack or Temporal迢ｬ閾ｪ繝舌Φ繝峨Λ繝ｼ・・  });
  await worker.run(); // 竊・縺薙ｌ縺梧ｭ｢縺ｾ繧九→Worker縺梧ｭｻ縺ｬ・亥・襍ｷ蜍輔・蛻･邂｡逅・ｼ・}
run().catch(err => { console.error(err); process.exit(1); });


// === 繝輔ぃ繧､繝ｫ4: run.ts・医け繝ｩ繧､繧｢繝ｳ繝医・5陦鯉ｼ・==
import { Client, Connection } from '@temporalio/client';
import { researchWorkflow } from './workflows';

const connection = await Connection.connect({ address: 'localhost:7233' });
const client = new Client({ connection });

const handle = await client.workflow.start(researchWorkflow, {
  taskQueue: 'research-queue',
  workflowId: `research-${Date.now()}`,
  args: ['LLM Durable Execution'],
});

const result = await handle.result();
// 竊・繧ｯ繝ｩ繝・す繝･閠先ｧ縺ｯTemporal縺瑚・蜍輔〒繧・ｋ・医％縺ｮ轤ｹ縺ｯ蜷後§・・
// 縺溘□縺励後←縺ｮ繧ｹ繝・ャ繝励∪縺ｧ螳御ｺ・＠縺溘°縲阪ｒ遒ｺ隱阪☆繧九↓縺ｯ
// Query繝上Φ繝峨Λ繝ｼ繧貞挨騾泌ｮ溯｣・☆繧句ｿ・ｦ√′縺ゅｋ・医＆繧峨↓+15陦鯉ｼ・```

**縺輔ｉ縺ｫ蠢・ｦ√↑繧ゅ・:**
```bash
# Temporal繧ｵ繝ｼ繝舌・縺ｮ襍ｷ蜍包ｼ・ocker縺ｾ縺溘・CLI蠢・茨ｼ・temporal server start-dev

# tsconfig.json 縺ｫ迚ｹ谿願ｨｭ螳夲ｼ・eplay縺ｮ縺溘ａ・・{
  "compilerOptions": {
    "module": "commonjs",  // ESModules縺ｯ菴ｿ縺医↑縺・宛邏・    ...
  }
}

# package.json 縺ｫwebpack險ｭ螳・or @temporalio/worker 縺ｮ繝舌Φ繝峨Λ繝ｼ險ｭ螳・```

---

## 繝舌・繧ｸ繝ｧ繝九Φ繧ｰ豈碑ｼ・ｼ域怙螟ｧ縺ｮ蟾ｮ・・
**繝ｦ繝ｼ繧ｹ繧ｱ繝ｼ繧ｹ: 譌｢蟄倥・螳溯｡後′襍ｰ縺｣縺ｦ縺・ｋ荳ｭ縺ｧ縲√計alidate縲阪せ繝・ャ繝励ｒ霑ｽ蜉縺励◆縺・*

### Nexum迚茨ｼ・陦瑚ｿｽ蜉縺吶ｋ縺縺托ｼ・```typescript
const researchWorkflowV2 = nexum.workflow('ResearchAgent')
  .effect('search', SearchResult, ...)
  .compute('validate', z.boolean(), (ctx) => {    // 竊・霑ｽ蜉
    return ctx.get('search').content.length > 10;  //   蝙句ｮ牙・縺ｫ蜑阪せ繝・ャ繝怜盾辣ｧ
  })
  .effect('summarize', Summary, ...)
  .build();

// nexum deploy 螳溯｡・竊・BREAKING縺ｨ讀懃衍 竊・譌ｧ繝舌・繧ｸ繝ｧ繝ｳ縺ｨ荳ｦ陦檎ｨｼ蜒搾ｼ郁・蜍包ｼ・// 譁ｰ縺励＞Execution縺ｯ閾ｪ蜍慕噪縺ｫV2 Worker縺ｸ繝ｫ繝ｼ繝・ぅ繝ｳ繧ｰ
```

### Temporal迚茨ｼ・etVersion蝨ｰ迯・ｼ・```typescript
export async function researchWorkflow(query: string) {
  const searchResult = await search(query);

  // 竊・In-flight縺ｮ繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ縺ｨ縺ｮ莠呈鋤諤ｧ繧剃ｿ昴▽縺溘ａ謇区嶌縺阪′蠢・ｦ・  const version = await getVersion(
    'add-validate-step',  // 繝舌・繧ｸ繝ｧ繝ｳ隴伜挨蟄撰ｼ域枚蟄怜・邂｡逅・′蠢・ｦ・ｼ・    DEFAULT_VERSION,       // 蜿､縺・Ρ繝ｼ繧ｯ繝輔Ο繝ｼ縺ｯ縺薙％
    1                      // 譁ｰ縺励＞繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ縺ｯ縺薙％
  );

  if (version >= 1) {
    // 譁ｰ縺励＞繧ｹ繝・ャ繝・    const isValid = await validate(searchResult.content);
    if (!isValid) {
      // 繝ｭ繝ｼ繝ｫ繝舌ャ繧ｯ蜃ｦ逅・ｂ謇区嶌縺・      await compensate(searchResult);
      return null;
    }
  }

  const summary = await summarize(searchResult.content);
  return summary;
}
// 竊・繧ｹ繝・ャ繝励ｒ霑ｽ蜉縺吶ｋ縺溘・縺ｫgetVersion()縺悟｢玲ｮ悶☆繧・// 蜊雁ｹｴ蠕後↓隱ｰ繧ゅ％縺ｮ繧ｳ繝ｼ繝峨ｒ隱ｭ繧√↑縺上↑繧・```

---

## 謨ｰ蛟､縺ｾ縺ｨ繧・
| 謖・ｨ・| Nexum | Temporal |
|------|-------|---------|
| 繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ螳夂ｾｩ縺ｮ繝輔ぃ繧､繝ｫ謨ｰ | 1 | 4 |
| 繝薙ず繝阪せ繝ｭ繧ｸ繝・け陦梧焚 | 10陦・| 48陦・|
| 繧､繝ｳ繝輔Λ蛻ｶ蠕｡繧ｳ繝ｼ繝芽｡梧焚 | 0陦・| 67陦・|
| 繝懊う繝ｩ繝ｼ繝励Ξ繝ｼ繝域ｯ皮紫 | 0% | 58% |
| 繝舌・繧ｸ繝ｧ繝ｳ霑ｽ蜉譎ゅ・霑ｽ蜉陦梧焚 | 3陦・| 15陦・ |
| 繧ｵ繝ｼ繝舌・繧ｻ繝・ヨ繧｢繝・・ | 荳崎ｦ・ｼ亥・阡ｵ・・| Docker/CLI蠢・・|
| LLM螟ｧ螳ｹ驥上・繧､繝ｭ繝ｼ繝牙ｯｾ蠢・| 閾ｪ蜍包ｼ・laim Check・・| 謇句虚螳溯｣・ｿ・・|
| 蝙区耳隲厄ｼ亥燕繧ｹ繝・ャ繝励・邨先棡・・| `ctx.get('search')` 縺ｧ閾ｪ蜍・| 謇句虚縺ｧ蠑墓焚縺ｨ縺励※貂｡縺・|

---

## 邨占ｫ・
**Temporal縺後後Λ繝・ヱ繝ｼ縺ｧ隗｣豎ｺ縺ｧ縺阪↑縺・咲炊逕ｱ:**

1. **History Size蛻ｶ髯・*: Temporal縺ｯ蜈ｨ繧ｹ繝・ャ繝励・蜈･蜃ｺ蜉帙ｒDB縺ｫ險倬鹸縺吶ｋ縲・LM縺ｮ蜃ｺ蜉幢ｼ域焚MB・峨ｒ隍・焚繧ｹ繝・ャ繝怜・闢・ｩ阪☆繧九→荳企剞・・0MB・峨↓驕斐☆繧九ょ屓驕ｿ縺ｫ縺ｯ迢ｬ閾ｪ縺ｮData Converter繧貞ｮ溯｣・☆繧句ｿ・ｦ√′縺ゅｊ縲√％繧後・縲卦emporal縺ｮ繝ｩ繝・ヱ繝ｼ縺ｧ縺ｪ縺蒐exum逶ｸ蠖薙・繧ゅ・繧定・蛻・〒菴懊ｋ縲堺ｽ懈･ｭ縺ｫ縺ｪ繧九・
2. **getVersion縺ｮ蠅玲ｮ・*: 繝舌・繧ｸ繝ｧ繝ｳ繧｢繝・・縺ｮ縺溘・縺ｫ繝ｯ繝ｼ繧ｯ繝輔Ο繝ｼ髢｢謨ｰ蜀・↓`getVersion()`蛻・ｲ舌′闢・ｩ阪＆繧後∝濠蟷ｴ蠕後↓縺ｯ菫晏ｮ井ｸ崎・縺ｫ縺ｪ繧九・exum縺ｯ荳ｦ陦檎ｨｼ蜒阪ｒ繧､繝ｳ繝輔Λ繝ｬ繝吶Ν縺ｧ隗｣豎ｺ縺励※縺・ｋ縺溘ａ縲√％縺ｮ蝠城｡後′逋ｺ逕溘＠縺ｪ縺・・
3. **LLM繝阪う繝・ぅ繝悶〒縺ｪ縺・*: Temporal縺ｯ縲悟・遲峨↑Activity縲阪ｒ蜑肴署縺ｨ縺吶ｋ縺後´LM縺ｯ譛ｬ雉ｪ逧・↓髱樊ｱｺ螳夂噪・亥酔縺伜・蜉帙〒繧ょ・蜉帙′螟峨ｏ繧具ｼ峨・exum縺ｯ`EFFECT_CALL`縺ｨ縺励※蜑ｯ菴懃畑繧呈・遉ｺ逧・↓蛻・屬縺励！dempotency Key繧定・蜍穂ｻ倅ｸ弱☆繧九％縺ｨ縺ｧ縺薙・蝠城｡後ｒ讒矩逧・↓隗｣豎ｺ縺励※縺・ｋ縲・
