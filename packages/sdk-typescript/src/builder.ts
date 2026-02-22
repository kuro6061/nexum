import { z } from 'zod';
import { zodToJsonSchema } from 'zod-to-json-schema';
import { createHash } from 'crypto';

export interface NodeDef {
  type: 'COMPUTE' | 'EFFECT' | 'ROUTER' | 'HUMAN_APPROVAL' | 'MAP' | 'REDUCE' | 'SUBWORKFLOW';
  dependencies: string[];
  outputSchema: object;
  zodSchema: z.ZodTypeAny;
  routes?: Array<{ condition: string; target: string }>;
  handler: (ctx: ExecutionContext<any, any>) => any | Promise<any>;
  itemsFn?: (ctx: ExecutionContext<any, any>) => any[];
  mapNodeId?: string;
  subWorkflowId?: string;
  inputFn?: (ctx: ExecutionContext<any, any>) => Record<string, unknown>;
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

export class WorkflowBuilder<
  TInput extends Record<string, any> = Record<string, any>,
  TNodes extends Record<string, any> = {}
> {
  private nodes: Record<string, NodeDef> = {};
  private nodeOrder: string[] = [];

  constructor(public readonly workflowId: string) {}

  input<T extends Record<string, any>>(): WorkflowBuilder<T, TNodes> {
    return this as any;
  }

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

export const nexum = {
  workflow: <TInput extends Record<string, any> = Record<string, any>>(id: string) =>
    new WorkflowBuilder<TInput>(id),
};
