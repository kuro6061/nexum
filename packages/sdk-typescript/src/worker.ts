import { BuiltWorkflow, ExecutionContext, NodeDef } from './builder.js';
import { createNexumClient, promisify } from './proto-client.js';

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

export class Worker {
  private running = false;
  private workflows = new Map<string, BuiltWorkflow>();
  private grpcClient: any = null;
  private completeTaskRpc: ((req: any) => Promise<any>) | null = null;
  private failTaskRpc: ((req: any) => Promise<any>) | null = null;
  private pollTaskRpc: ((req: any) => Promise<any>) | null = null;

  constructor(
    private serverAddress = 'localhost:50051',
    private workerId = 'worker-' + Math.random().toString(36).slice(2),
    private concurrency = 4
  ) {}

  register(workflow: BuiltWorkflow) {
    this.workflows.set(
      `${workflow.workflowId}:${workflow.versionHash}`,
      workflow
    );
  }

  async start() {
    const client = createNexumClient(this.serverAddress);
    this.grpcClient = client;
    const registerWorkflow = promisify<any, any>(client, 'registerWorkflow');
    this.pollTaskRpc = promisify<any, any>(client, 'pollTask');
    this.completeTaskRpc = promisify<any, any>(client, 'completeTask');
    this.failTaskRpc = promisify<any, any>(client, 'failTask');

    // Register all workflows
    for (const workflow of this.workflows.values()) {
      const response = await registerWorkflow({
        workflowId: workflow.workflowId,
        versionHash: workflow.versionHash,
        irJson: workflow.irJson,
      });
      const compat = response?.compatibility;
      if (compat === 'BREAKING') {
        console.warn(`[NEXUM] BREAKING change detected for ${workflow.workflowId}. Run old workers until in-flight executions complete.`);
      } else if (compat === 'SAFE') {
        console.log(`[NEXUM] SAFE change for ${workflow.workflowId}. New nodes added.`);
      } else if (compat === 'IDENTICAL') {
        console.log(`[NEXUM] No changes for ${workflow.workflowId}.`);
      } else if (compat) {
        console.log(`[NEXUM] New workflow ${workflow.workflowId} registered.`);
      }
    }

    this.running = true;

    let activeSlots = 0;

    const poll = async () => {
      while (this.running) {
        if (activeSlots >= this.concurrency) {
          await sleep(100);
          continue;
        }

        const task = await this.pollOnce();
        if (!task) {
          await sleep(500);
          continue;
        }

        activeSlots++;
        this.processTask(task)
          .catch(e => console.error('[NEXUM] Task error:', e))
          .finally(() => { activeSlots--; });
      }
    };

    poll();
  }

  private async pollOnce(): Promise<{
    taskId: string;
    executionId: string;
    nodeId: string;
    inputJson: string;
    idempotencyKey: string;
    nodeType: string;
    isMapSubtask: boolean;
    mapItemJson: string;
    mapIndex: number;
    mapTotal: number;
    workflow: BuiltWorkflow;
  } | null> {
    try {
      for (const workflow of this.workflows.values()) {
        if (!this.running) return null;

        const resp = await this.pollTaskRpc!({
          workerId: this.workerId,
          versionHash: workflow.versionHash,
        });

        if (resp.hasTask) {
          return {
            taskId: resp.taskId,
            executionId: resp.executionId,
            nodeId: resp.nodeId,
            inputJson: resp.inputJson,
            idempotencyKey: resp.idempotencyKey,
            nodeType: resp.nodeType || '',
            isMapSubtask: resp.isMapSubtask || false,
            mapItemJson: resp.mapItemJson || '',
            mapIndex: resp.mapIndex || 0,
            mapTotal: resp.mapTotal || 0,
            workflow,
          };
        }
      }
    } catch (err: any) {
      if (this.running) {
        // Connection error - server might not be ready yet
      }
    }
    return null;
  }

  private async processTask(task: {
    taskId: string;
    executionId: string;
    nodeId: string;
    inputJson: string;
    idempotencyKey: string;
    nodeType: string;
    isMapSubtask: boolean;
    mapItemJson: string;
    mapIndex: number;
    mapTotal: number;
    workflow: BuiltWorkflow;
  }) {
    const nodeDef = task.workflow.handlers[task.nodeId];

    // HUMAN_APPROVAL: don't execute, just wait for external approval
    if (nodeDef?.type === 'HUMAN_APPROVAL') {
      console.log(`[NEXUM] \u23F8 Waiting for human approval: ${task.nodeId} (execution: ${task.executionId})`);
      return;
    }

    // SUBWORKFLOW coordinator: evaluate input function and return to server
    if (nodeDef?.type === 'SUBWORKFLOW') {
      const inputData = JSON.parse(task.inputJson || '{}');
      const ctx: ExecutionContext<any, any> = {
        input: inputData.input,
        get(nodeId: string) {
          return inputData.deps?.[nodeId];
        },
        getMapResults(mapNodeId: string) {
          const output = inputData.deps?.[mapNodeId];
          if (!Array.isArray(output)) throw new Error(`${mapNodeId} is not a MAP node or not completed`);
          return output;
        },
      };

      const childInput = nodeDef.inputFn!(ctx);
      await this.completeTaskRpc!({
        taskId: task.taskId,
        outputJson: JSON.stringify({
          subWorkflowId: nodeDef.subWorkflowId,
          childInput,
        }),
      });
      console.log(`[NEXUM] \u23F8 SUBWORKFLOW: ${nodeDef.subWorkflowId} started, parent waiting...`);
      return;
    }

    if (!nodeDef) {
      await this.failTaskRpc!({
        taskId: task.taskId,
        errorMessage: `No handler for node: ${task.nodeId}`,
      });
      return;
    }

    try {
      const inputData = JSON.parse(task.inputJson || '{}');

      const ctx: ExecutionContext<any, any> = {
        input: inputData.input,
        get(nodeId: string) {
          return inputData.deps?.[nodeId];
        },
        getMapResults(mapNodeId: string) {
          const output = inputData.deps?.[mapNodeId];
          if (!Array.isArray(output)) throw new Error(`${mapNodeId} is not a MAP node or not completed`);
          return output;
        },
      };

      // MAP coordinator (phase 1): evaluate items source, return array
      if (task.nodeType === 'MAP' && nodeDef.type === 'MAP' && !task.isMapSubtask) {
        const items = nodeDef.itemsFn!(ctx);
        console.log(`[NEXUM] Starting MAP: ${task.nodeId} (${items.length} items)`);
        await this.completeTaskRpc!({
          taskId: task.taskId,
          outputJson: JSON.stringify(items),
        });
        return;
      }

      // MAP sub-task (phase 2): run handler for single item
      if (task.nodeType === 'MAP_SUBTASK' && nodeDef.type === 'MAP') {
        const item = JSON.parse(task.mapItemJson);
        console.log(`[NEXUM] MAP sub-task ${task.nodeId}[${task.mapIndex}]: ${typeof item === 'string' ? item.substring(0, 50) : JSON.stringify(item).substring(0, 50)}`);
        const result = await (nodeDef.handler as any)(ctx, item, task.mapIndex);
        nodeDef.zodSchema.parse(result);
        await this.completeTaskRpc!({
          taskId: task.taskId,
          outputJson: JSON.stringify(result),
        });
        return;
      }

      // REDUCE: run reducer with all map results available via ctx
      if (task.nodeType === 'REDUCE' && nodeDef.type === 'REDUCE') {
        const result = await nodeDef.handler(ctx);
        nodeDef.zodSchema.parse(result);
        await this.completeTaskRpc!({
          taskId: task.taskId,
          outputJson: JSON.stringify(result),
        });
        console.log(`[NEXUM] REDUCE complete: ${task.nodeId}`);
        return;
      }

      // Default: COMPUTE/EFFECT
      const rawOutput = await nodeDef.handler(ctx);

      // Validate output against Zod schema
      if (nodeDef.zodSchema) {
        nodeDef.zodSchema.parse(rawOutput);
      }

      await this.completeTaskRpc!({
        taskId: task.taskId,
        outputJson: JSON.stringify(rawOutput),
      });
    } catch (err: any) {
      await this.failTaskRpc!({
        taskId: task.taskId,
        errorMessage: err.message || String(err),
      });
    }
  }

  stop() {
    this.running = false;
  }
}
