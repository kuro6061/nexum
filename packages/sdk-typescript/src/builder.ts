import { z } from 'zod';
import { zodToJsonSchema } from 'zod-to-json-schema';
import { createHash } from 'crypto';

export interface NodeDef {
  type: 'COMPUTE' | 'EFFECT' | 'ROUTER' | 'HUMAN_APPROVAL' | 'MAP' | 'REDUCE' | 'SUBWORKFLOW' | 'TIMER';
  dependencies: string[];
  outputSchema: object;
  zodSchema: z.ZodTypeAny;
  routes?: Array<{ condition: string; target: string }>;
  handler: (ctx: ExecutionContext<any, any>) => any | Promise<any>;
  itemsFn?: (ctx: ExecutionContext<any, any>) => any[];
  mapNodeId?: string;
  subWorkflowId?: string;
  inputFn?: (ctx: ExecutionContext<any, any>) => Record<string, unknown>;
  delaySeconds?: number;
}

export interface ExecutionContext<
  TInput extends Record<string, any>,
  TNodes extends Record<string, any>
> {
  input: TInput;
  get<K extends string & keyof TNodes>(nodeId: K): TNodes[K];
  getMapResults<K extends string & keyof TNodes>(mapNodeId: K): TNodes[K];
}

export interface BuiltWorkflow {
  workflowId: string;
  versionHash: string;
  irJson: string;
  handlers: Record<string, NodeDef>;
}

/**
 * Fluent builder for defining a Nexum workflow.
 *
 * @example
 * ```ts
 * const wf = nexum.workflow<{ query: string }>('my-workflow')
 *   .effect('search', SearchResult, async ctx => fetchData(ctx.input.query))
 *   .compute('summarize', Summary, ctx => summarize(ctx.get('search')))
 *   .build();
 * ```
 */
export class WorkflowBuilder<
  TInput extends Record<string, any> = Record<string, any>,
  TNodes extends Record<string, any> = {}
> {
  private nodes: Record<string, NodeDef> = {};
  private nodeOrder: string[] = [];

  constructor(public readonly workflowId: string) {}

  /** Declare the input type for this workflow (type-level only, no runtime effect). */
  input<T extends Record<string, any>>(): WorkflowBuilder<T, TNodes> {
    return this as any;
  }

  /**
   * Add a **COMPUTE** node — a pure, deterministic function.
   * Depends on all preceding nodes by default.
   * Compute nodes are not retried on failure.
   */
  compute<K extends string, TSchema extends z.ZodTypeAny>(
    id: K,
    schema: TSchema,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => z.infer<TSchema>
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TSchema>>> {
    this.nodes[id] = {
      type: 'COMPUTE',
      dependencies: [...this.nodeOrder],
      outputSchema: zodToJsonSchema(schema) as object,
      zodSchema: schema,
      handler,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add an **EFFECT** node — a side-effectful async operation (API call, DB write, etc.).
   * Executed with **exactly-once** semantics and automatic retry with exponential backoff.
   * Depends on all preceding nodes by default.
   */
  effect<K extends string, TSchema extends z.ZodTypeAny>(
    id: K,
    schema: TSchema,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => Promise<z.infer<TSchema>>
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TSchema>>> {
    this.nodes[id] = {
      type: 'EFFECT',
      dependencies: [...this.nodeOrder],
      outputSchema: zodToJsonSchema(schema) as object,
      zodSchema: schema,
      handler,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add a **HUMAN_APPROVAL** node — pauses the workflow until a human approves or rejects.
   * Use `nexum approve <executionId> <nodeId>` or the CLI `nexum approvals` to act on pending requests.
   */
  humanApproval<K extends string>(
    id: K,
    _options?: { approvers?: string[]; message?: string }
  ): WorkflowBuilder<TInput, TNodes & Record<K, { approved: boolean; approver: string; comment: string }>> {
    this.nodes[id] = {
      type: 'HUMAN_APPROVAL',
      dependencies: [...this.nodeOrder],
      outputSchema: {
        type: 'object',
        properties: {
          approved: { type: 'boolean' },
          approver: { type: 'string' },
          comment: { type: 'string' },
        },
      },
      zodSchema: z.object({ approved: z.boolean(), approver: z.string(), comment: z.string() }),
      handler: () => { throw new Error('HUMAN_APPROVAL nodes are handled by the server'); },
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /** Add a **COMPUTE** node with explicit dependencies instead of the default sequential chain. */
  computeAfter<K extends string, TSchema extends z.ZodTypeAny>(
    id: K,
    dependsOn: string[],
    schema: TSchema,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => z.infer<TSchema>
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TSchema>>> {
    this.nodes[id] = {
      type: 'COMPUTE',
      dependencies: dependsOn,
      outputSchema: zodToJsonSchema(schema) as object,
      zodSchema: schema,
      handler,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add a **ROUTER** node — dynamically routes execution to one branch based on LLM output or logic.
   * Only the selected branch is executed; all other branches are skipped.
   */
  router<K extends string>(
    id: K,
    routes: Array<{ condition: string; target: string }>,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => { routed_to: string }
  ): WorkflowBuilder<TInput, TNodes & Record<K, { routed_to: string }>> {
    this.nodes[id] = {
      type: 'ROUTER',
      dependencies: [...this.nodeOrder],
      outputSchema: { type: 'object', properties: { routed_to: { type: 'string' } } },
      zodSchema: z.object({ routed_to: z.string() }),
      routes,
      handler,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  routerAfter<K extends string>(
    id: K,
    dependsOn: string[],
    routes: Array<{ condition: string; target: string }>,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => { routed_to: string }
  ): WorkflowBuilder<TInput, TNodes & Record<K, { routed_to: string }>> {
    this.nodes[id] = {
      type: 'ROUTER',
      dependencies: dependsOn,
      outputSchema: { type: 'object', properties: { routed_to: { type: 'string' } } },
      zodSchema: z.object({ routed_to: z.string() }),
      routes,
      handler,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /** Add an **EFFECT** node with explicit dependencies (fan-in, parallel join). */
  effectAfter<K extends string, TSchema extends z.ZodTypeAny>(
    id: K,
    dependsOn: string[],
    schema: TSchema,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => Promise<z.infer<TSchema>>
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TSchema>>> {
    this.nodes[id] = {
      type: 'EFFECT',
      dependencies: dependsOn,
      outputSchema: zodToJsonSchema(schema) as object,
      zodSchema: schema,
      handler,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add a **MAP** node — fans out over a list, executing the handler for each item in parallel.
   * Pair with `.reduce()` to aggregate results.
   */
  map<K extends string, TItem, TOut extends z.ZodTypeAny>(
    id: K,
    outputSchema: TOut,
    options: {
      items: (ctx: ExecutionContext<TInput, TNodes>) => TItem[];
      handler: (ctx: ExecutionContext<TInput, TNodes>, item: TItem, index: number) => Promise<z.infer<TOut>>;
    }
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TOut>[]>> {
    this.nodes[id] = {
      type: 'MAP',
      dependencies: [...this.nodeOrder],
      outputSchema: zodToJsonSchema(outputSchema) as object,
      zodSchema: outputSchema,
      handler: options.handler as any,
      itemsFn: options.items as any,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add a **REDUCE** node — aggregates results from the preceding MAP node.
   * Must immediately follow a `.map()` call.
   */
  reduce<K extends string, TOut extends z.ZodTypeAny>(
    id: K,
    outputSchema: TOut,
    handler: (ctx: ExecutionContext<TInput, TNodes>) => z.infer<TOut> | Promise<z.infer<TOut>>
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TOut>>> {
    // Find the most recent MAP node to link to
    const lastMapNode = [...this.nodeOrder].reverse().find(nId => this.nodes[nId]?.type === 'MAP');
    if (!lastMapNode) throw new Error('reduce() must follow a map() node');
    this.nodes[id] = {
      type: 'REDUCE',
      dependencies: [lastMapNode],
      outputSchema: zodToJsonSchema(outputSchema) as object,
      zodSchema: outputSchema,
      handler,
      mapNodeId: lastMapNode,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add a **SUBWORKFLOW** node — invokes another workflow as a step.
   * The parent workflow waits for the child to complete before proceeding.
   */
  subworkflow<K extends string, TOut extends z.ZodTypeAny>(
    id: K,
    outputSchema: TOut,
    options: {
      workflow: { workflowId: string; nodes?: any };
      input: (ctx: ExecutionContext<TInput, TNodes>) => Record<string, unknown>;
    }
  ): WorkflowBuilder<TInput, TNodes & Record<K, z.infer<TOut>>> {
    this.nodes[id] = {
      type: 'SUBWORKFLOW',
      dependencies: [...this.nodeOrder],
      outputSchema: zodToJsonSchema(outputSchema) as object,
      zodSchema: outputSchema,
      handler: () => { throw new Error('SUBWORKFLOW nodes are handled by the server'); },
      subWorkflowId: options.workflow.workflowId,
      inputFn: options.input,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Add a **TIMER** node — waits for a specified duration before proceeding.
   * The server handles the delay durably; no worker is needed.
   *
   * @example
   * ```ts
   * .timer('wait-5min', { delaySeconds: 300 })
   * .timer('send-at', { scheduledAt: new Date('2026-01-01T09:00:00Z') })
   * ```
   */
  timer<K extends string>(
    id: K,
    options: { delaySeconds: number } | { scheduledAt: Date }
  ): WorkflowBuilder<TInput, TNodes & Record<K, { waited_until: string; delay_seconds: number }>> {
    const delaySeconds = 'delaySeconds' in options
      ? options.delaySeconds
      : Math.max(0, Math.floor((options.scheduledAt.getTime() - Date.now()) / 1000));
    this.nodes[id] = {
      type: 'TIMER',
      dependencies: [...this.nodeOrder],
      outputSchema: {
        type: 'object',
        properties: {
          waited_until: { type: 'string' },
          delay_seconds: { type: 'number' },
        },
      },
      zodSchema: z.object({ waited_until: z.string(), delay_seconds: z.number() }),
      handler: () => { throw new Error('TIMER nodes are handled by the server'); },
      delaySeconds,
    };
    this.nodeOrder.push(id);
    return this as any;
  }

  /**
   * Compile the workflow definition into a `BuiltWorkflow`.
   * Computes a deterministic SHA-256 `versionHash` from the IR JSON,
   * enabling safe version upgrades and exactly-once execution.
   */
  build(): BuiltWorkflow {
    const irNodes: Record<string, any> = {};
    for (const [id, def] of Object.entries(this.nodes)) {
      irNodes[id] = {
        type: def.type,
        dependencies: def.dependencies,
        ...(def.routes ? { routes: def.routes } : {}),
        ...(def.mapNodeId ? { mapNodeId: def.mapNodeId } : {}),
        ...(def.subWorkflowId ? { subWorkflowId: def.subWorkflowId } : {}),
        ...(def.inputFn ? { inputFn: def.inputFn.toString() } : {}),
        ...(def.delaySeconds !== undefined ? { delay_seconds: def.delaySeconds } : {}),
      };
    }
    const irJson = JSON.stringify({ nodes: irNodes });
    const versionHash = 'sha256:' + createHash('sha256').update(irJson).digest('hex');
    return {
      workflowId: this.workflowId,
      versionHash,
      irJson,
      handlers: this.nodes,
    };
  }
}

/**
 * Entry point for the Nexum SDK.
 *
 * @example
 * ```ts
 * import { nexum } from 'nexum-js';
 *
 * const myWorkflow = nexum.workflow('my-workflow')
 *   .effect('fetch', FetchResult, async ctx => fetch(ctx.input.url))
 *   .compute('process', ProcessResult, ctx => process(ctx.get('fetch')))
 *   .build();
 * ```
 */
export const nexum = {
  /** Create a new workflow builder with the given workflow ID. */
  workflow: <TInput extends Record<string, any> = Record<string, any>>(id: string) =>
    new WorkflowBuilder<TInput>(id),
};
