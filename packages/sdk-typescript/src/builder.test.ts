import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { nexum } from './index.js';

// ──────────────────────────────────────────────────────────────────
// Helper: build a parsed IR object from a BuiltWorkflow
// ──────────────────────────────────────────────────────────────────
function ir(wf: ReturnType<ReturnType<typeof nexum.workflow>['build']>) {
  return JSON.parse(wf.irJson) as {
    nodes: Record<string, { type: string; dependencies: string[]; [k: string]: unknown }>;
  };
}

// ──────────────────────────────────────────────────────────────────
// 1. 基本的なチェーン: 依存関係が順番通りに設定される
// ──────────────────────────────────────────────────────────────────
describe('WorkflowBuilder - basic chain', () => {
  it('compute nodes get sequential dependencies', () => {
    const wf = nexum
      .workflow('test-chain')
      .compute('a', z.object({ x: z.number() }), () => ({ x: 1 }))
      .compute('b', z.object({ y: z.number() }), () => ({ y: 2 }))
      .compute('c', z.object({ z: z.number() }), () => ({ z: 3 }))
      .build();

    const nodes = ir(wf).nodes;
    expect(nodes['a'].dependencies).toEqual([]);
    expect(nodes['b'].dependencies).toEqual(['a']);
    expect(nodes['c'].dependencies).toEqual(['a', 'b']);
  });

  it('effect nodes get sequential dependencies', () => {
    const wf = nexum
      .workflow('test-effects')
      .effect('fetch', z.object({ data: z.string() }), async () => ({ data: 'ok' }))
      .effect('save', z.object({ id: z.string() }), async () => ({ id: '1' }))
      .build();

    const nodes = ir(wf).nodes;
    expect(nodes['fetch'].dependencies).toEqual([]);
    expect(nodes['save'].dependencies).toEqual(['fetch']);
  });

  it('node types are correctly set in IR', () => {
    const wf = nexum
      .workflow('test-types')
      .compute('c', z.object({ v: z.string() }), () => ({ v: '' }))
      .effect('e', z.object({ v: z.string() }), async () => ({ v: '' }))
      .build();

    const nodes = ir(wf).nodes;
    expect(nodes['c'].type).toBe('COMPUTE');
    expect(nodes['e'].type).toBe('EFFECT');
  });
});

// ──────────────────────────────────────────────────────────────────
// 2. effectAfter / computeAfter: 明示的な依存関係
// ──────────────────────────────────────────────────────────────────
describe('WorkflowBuilder - explicit dependencies (effectAfter)', () => {
  it('effectAfter sets exactly the specified deps (fan-in)', () => {
    const wf = nexum
      .workflow('fan-in')
      .effect('a', z.object({ v: z.number() }), async () => ({ v: 1 }))
      .effect('b', z.object({ v: z.number() }), async () => ({ v: 2 }))
      .effectAfter('merge', ['a', 'b'], z.object({ sum: z.number() }), async () => ({ sum: 3 }))
      .build();

    const nodes = ir(wf).nodes;
    expect(nodes['a'].dependencies).toEqual([]);
    expect(nodes['b'].dependencies).toEqual(['a']);
    expect(nodes['merge'].dependencies).toEqual(['a', 'b']);
  });

  it('computeAfter overrides sequential deps', () => {
    const wf = nexum
      .workflow('compute-after')
      .compute('x', z.object({ v: z.number() }), () => ({ v: 1 }))
      .compute('y', z.object({ v: z.number() }), () => ({ v: 2 }))
      .computeAfter('z', ['x'], z.object({ v: z.number() }), () => ({ v: 3 }))
      .build();

    // z depends only on x, not y
    expect(ir(wf).nodes['z'].dependencies).toEqual(['x']);
  });
});

// ──────────────────────────────────────────────────────────────────
// 3. ROUTER ノード
// ──────────────────────────────────────────────────────────────────
describe('WorkflowBuilder - router', () => {
  it('router node has correct type and routes', () => {
    const wf = nexum
      .workflow('router-test')
      .compute('analyze', z.object({ score: z.number() }), () => ({ score: 0.9 }))
      .router(
        'decide',
        [
          { condition: 'score > 0.8', target: 'approve' },
          { condition: 'score <= 0.8', target: 'reject' },
        ],
        () => ({ routed_to: 'approve' })
      )
      .build();

    const node = ir(wf).nodes['decide'];
    expect(node.type).toBe('ROUTER');
    expect(node.routes).toHaveLength(2);
    expect((node.routes as any[])[0].target).toBe('approve');
    expect((node.routes as any[])[1].target).toBe('reject');
  });
});

// ──────────────────────────────────────────────────────────────────
// 4. MAP / REDUCE
// ──────────────────────────────────────────────────────────────────
describe('WorkflowBuilder - map/reduce', () => {
  it('map node has MAP type, reduce has REDUCE type with mapNodeId', () => {
    const wf = nexum
      .workflow('map-reduce-test')
      .map('process', z.object({ result: z.string() }), {
        items: () => [1, 2, 3],
        handler: async (_ctx, item) => ({ result: String(item) }),
      })
      .reduce('aggregate', z.object({ total: z.number() }), () => ({ total: 3 }))
      .build();

    const nodes = ir(wf).nodes;
    expect(nodes['process'].type).toBe('MAP');
    expect(nodes['aggregate'].type).toBe('REDUCE');
    expect(nodes['aggregate'].mapNodeId).toBe('process');
    expect(nodes['aggregate'].dependencies).toEqual(['process']);
  });
});

// ──────────────────────────────────────────────────────────────────
// 5. HUMAN_APPROVAL / TIMER / SUBWORKFLOW
// ──────────────────────────────────────────────────────────────────
describe('WorkflowBuilder - special node types', () => {
  it('humanApproval node has HUMAN_APPROVAL type', () => {
    const wf = nexum
      .workflow('approval-test')
      .compute('prepare', z.object({ amount: z.number() }), () => ({ amount: 1000 }))
      .humanApproval('approve')
      .build();

    const nodes = ir(wf).nodes;
    expect(nodes['approve'].type).toBe('HUMAN_APPROVAL');
    expect(nodes['approve'].dependencies).toEqual(['prepare']);
  });

  it('timer node has TIMER type and delay_seconds', () => {
    const wf = nexum
      .workflow('timer-test')
      .effect('step1', z.object({ ok: z.boolean() }), async () => ({ ok: true }))
      .timer('wait', { delaySeconds: 300 })
      .build();

    const node = ir(wf).nodes['wait'];
    expect(node.type).toBe('TIMER');
    expect(node.delay_seconds).toBe(300);
    expect(node.dependencies).toEqual(['step1']);
  });

  it('subworkflow node has SUBWORKFLOW type and subWorkflowId', () => {
    const childWf = nexum
      .workflow('child-wf')
      .compute('do', z.object({ done: z.boolean() }), () => ({ done: true }))
      .build();

    const wf = nexum
      .workflow('parent-wf')
      .subworkflow('run-child', z.object({ done: z.boolean() }), {
        workflow: childWf,
        input: () => ({}),
      })
      .build();

    const node = ir(wf).nodes['run-child'];
    expect(node.type).toBe('SUBWORKFLOW');
    expect(node.subWorkflowId).toBe('child-wf');
  });
});

// ──────────────────────────────────────────────────────────────────
// 6. build() の出力: versionHash と irJson
// ──────────────────────────────────────────────────────────────────
describe('WorkflowBuilder - build output', () => {
  it('versionHash is sha256: prefixed and deterministic', () => {
    const wf1 = nexum
      .workflow('det-test')
      .compute('a', z.object({ v: z.number() }), () => ({ v: 1 }))
      .build();

    const wf2 = nexum
      .workflow('det-test')
      .compute('a', z.object({ v: z.number() }), () => ({ v: 1 }))
      .build();

    expect(wf1.versionHash).toMatch(/^sha256:/);
    expect(wf1.versionHash).toBe(wf2.versionHash);
  });

  it('different nodes produce different versionHash', () => {
    const wf1 = nexum
      .workflow('diff-test')
      .compute('a', z.object({ v: z.number() }), () => ({ v: 1 }))
      .build();

    const wf2 = nexum
      .workflow('diff-test')
      .compute('b', z.object({ v: z.number() }), () => ({ v: 1 }))
      .build();

    expect(wf1.versionHash).not.toBe(wf2.versionHash);
  });

  it('handlers are accessible by node id', () => {
    const handler = () => ({ v: 42 });
    const wf = nexum
      .workflow('handler-test')
      .compute('node1', z.object({ v: z.number() }), handler)
      .build();

    expect(wf.handlers['node1'].handler).toBe(handler);
  });

  it('irJson is valid JSON', () => {
    const wf = nexum
      .workflow('json-test')
      .compute('a', z.object({ x: z.string() }), () => ({ x: '' }))
      .build();

    expect(() => JSON.parse(wf.irJson)).not.toThrow();
  });
});
