# Nexum vs Temporal: コード量比較

同じユースケース：「search → summarize の2ステップエージェント + Workerクラッシュ耐性」

---

## Nexum版（実際に動いたコード）

**ファイル数: 1ファイル / 合計: 62行**

```typescript
// examples/demo/run.ts — これだけ
import { nexum, Worker, NexumClient } from '@nexum/sdk';
import { z } from 'zod';

// ① スキーマ定義（2行）
const SearchResult = z.object({ content: z.string() });
const Summary = z.object({ score: z.number(), text: z.string() });

// ② ワークフロー定義（10行）
const researchWorkflow = nexum.workflow('ResearchAgent')
  .effect('search', SearchResult, async (ctx) => {
    return { content: 'Research about: ' + ctx.input.query };
  })
  .effect('summarize', Summary, async (ctx) => {
    return { score: 88, text: 'Summary of: ' + ctx.get('search').content };
    //                                                    ^^^^^^^^^^^^
    //                                              型安全に前ステップの結果を取得
  })
  .build();

// ③ 実行（Worker起動 + 実行開始）（10行）
const worker1 = new Worker('localhost:50051', 'worker-1');
worker1.register(researchWorkflow);
await worker1.start();
const executionId = await client.startExecution(...);

// ④ クラッシュ & 復旧（8行）
worker1.stop(); // クラッシュ擬似
const worker2 = new Worker('localhost:50051', 'worker-2');
worker2.register(researchWorkflow);
worker2.start(); // → 自動的に summarize から再開
```

---

## Temporal版（同等のことをやるコード）

**ファイル数: 4ファイル / 合計: 115行 + 設定ファイル**

```typescript
// === ファイル1: activities.ts（20行）===
// Temporalはアクティビティとワークフローを必ず分離する必要がある
import { ActivityCancellationType } from '@temporalio/activity';

export async function search(query: string): Promise<{ content: string }> {
  // アクティビティはワークフローと別ファイルに書かないといけない制約
  return { content: 'Research about: ' + query };
}

export async function summarize(content: string): Promise<{ score: number; text: string }> {
  return { score: 88, text: 'Summary of: ' + content };
}
// ↑ ctx.get() のような型推論はない。引数を手動で渡す必要がある


// === ファイル2: workflows.ts（28行）===
import { proxyActivities } from '@temporalio/workflow';
import type * as activities from './activities';

// アクティビティを「プロキシ」経由で呼ぶ（ラッパーが必要）
const { search, summarize } = proxyActivities<typeof activities>({
  startToCloseTimeout: '1 minute',
  retry: { maximumAttempts: 3 },
});

export async function researchWorkflow(query: string) {
  const searchResult = await search(query);      // ← 型: { content: string }
  const summary = await summarize(searchResult.content); // ← 手動でデータを繋ぐ
  return summary;
}
// ↑ これで良いが、LLMの出力（数MB）をそのまま返すと
//   Temporalの History Size Limit（50MB）に引っかかる可能性がある


// === ファイル3: worker.ts（20行）===
import { Worker } from '@temporalio/worker';
import * as activities from './activities';

async function run() {
  const worker = await Worker.create({
    workflowsPath: require.resolve('./workflows'),
    activities,
    taskQueue: 'research-queue',
    // ↑ bundler設定が必要（webpack or Temporal独自バンドラー）
  });
  await worker.run(); // ← これが止まるとWorkerが死ぬ（再起動は別管理）
}
run().catch(err => { console.error(err); process.exit(1); });


// === ファイル4: run.ts（クライアント、25行）===
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
// ↑ クラッシュ耐性はTemporalが自動でやる（この点は同じ）

// ただし「どのステップまで完了したか」を確認するには
// Queryハンドラーを別途実装する必要がある（さらに+15行）
```

**さらに必要なもの:**
```bash
# Temporalサーバーの起動（DockerまたはCLI必須）
temporal server start-dev

# tsconfig.json に特殊設定（Replayのため）
{
  "compilerOptions": {
    "module": "commonjs",  // ESModulesは使えない制約
    ...
  }
}

# package.json にwebpack設定 or @temporalio/worker のバンドラー設定
```

---

## バージョニング比較（最大の差）

**ユースケース: 既存の実行が走っている中で、「validate」ステップを追加したい**

### Nexum版（3行追加するだけ）
```typescript
const researchWorkflowV2 = nexum.workflow('ResearchAgent')
  .effect('search', SearchResult, ...)
  .compute('validate', z.boolean(), (ctx) => {    // ← 追加
    return ctx.get('search').content.length > 10;  //   型安全に前ステップ参照
  })
  .effect('summarize', Summary, ...)
  .build();

// nexum deploy 実行 → BREAKINGと検知 → 旧バージョンと並行稼働（自動）
// 新しいExecutionは自動的にV2 Workerへルーティング
```

### Temporal版（getVersion地獄）
```typescript
export async function researchWorkflow(query: string) {
  const searchResult = await search(query);

  // ↓ In-flightのワークフローとの互換性を保つため手書きが必要
  const version = await getVersion(
    'add-validate-step',  // バージョン識別子（文字列管理が必要）
    DEFAULT_VERSION,       // 古いワークフローはここ
    1                      // 新しいワークフローはここ
  );

  if (version >= 1) {
    // 新しいステップ
    const isValid = await validate(searchResult.content);
    if (!isValid) {
      // ロールバック処理も手書き
      await compensate(searchResult);
      return null;
    }
  }

  const summary = await summarize(searchResult.content);
  return summary;
}
// ↑ ステップを追加するたびにgetVersion()が増殖する
// 半年後に誰もこのコードを読めなくなる
```

---

## 数値まとめ

| 指標 | Nexum | Temporal |
|------|-------|---------|
| ワークフロー定義のファイル数 | 1 | 4 |
| ビジネスロジック行数 | 10行 | 48行 |
| インフラ制御コード行数 | 0行 | 67行 |
| ボイラープレート比率 | 0% | 58% |
| バージョン追加時の追加行数 | 3行 | 15行+ |
| サーバーセットアップ | 不要（内蔵） | Docker/CLI必須 |
| LLM大容量ペイロード対応 | 自動（Claim Check） | 手動実装必須 |
| 型推論（前ステップの結果） | `ctx.get('search')` で自動 | 手動で引数として渡す |

---

## 結論

**Temporalが「ラッパーで解決できない」理由:**

1. **History Size制限**: Temporalは全ステップの入出力をDBに記録する。LLMの出力（数MB）を複数ステップ分蓄積すると上限（50MB）に達する。回避には独自のData Converterを実装する必要があり、これは「TemporalのラッパーでなくNexum相当のものを自分で作る」作業になる。

2. **getVersionの増殖**: バージョンアップのたびにワークフロー関数内に`getVersion()`分岐が蓄積され、半年後には保守不能になる。Nexumは並行稼働をインフラレベルで解決しているため、この問題が発生しない。

3. **LLMネイティブでない**: Temporalは「冪等なActivity」を前提とするが、LLMは本質的に非決定的（同じ入力でも出力が変わる）。Nexumは`EFFECT_CALL`として副作用を明示的に分離し、Idempotency Keyを自動付与することでこの問題を構造的に解決している。
