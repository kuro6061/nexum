import { createNexumClient, promisify } from './proto-client.js';

export interface ExecutionSummary {
  executionId: string;
  workflowId: string;
  versionHash: string;
  status: string;
  createdAt: string;
}

export interface VersionInfo {
  workflowId: string;
  versionHash: string;
  compatibility: string;
  registeredAt: string;
  activeExecutions: number;
}

export interface PendingApproval {
  executionId: string;
  nodeId: string;
  workflowId: string;
  startedAt: string;
}

export class NexumClient {
  private client: any;
  private startExecutionRpc: (req: any) => Promise<any>;
  private getStatusRpc: (req: any) => Promise<any>;
  private listExecutionsRpc: (req: any) => Promise<any>;
  private cancelExecutionRpc: (req: any) => Promise<any>;
  private listWorkflowVersionsRpc: (req: any) => Promise<any>;
  private approveTaskRpc: (req: any) => Promise<any>;
  private rejectTaskRpc: (req: any) => Promise<any>;
  private getPendingApprovalsRpc: (req: any) => Promise<any>;

  constructor(private serverAddress = 'localhost:50051') {
    this.client = createNexumClient(serverAddress);
    this.startExecutionRpc = promisify(this.client, 'startExecution');
    this.getStatusRpc = promisify(this.client, 'getStatus');
    this.listExecutionsRpc = promisify(this.client, 'listExecutions');
    this.cancelExecutionRpc = promisify(this.client, 'cancelExecution');
    this.listWorkflowVersionsRpc = promisify(this.client, 'listWorkflowVersions');
    this.approveTaskRpc = promisify(this.client, 'approveTask');
    this.rejectTaskRpc = promisify(this.client, 'rejectTask');
    this.getPendingApprovalsRpc = promisify(this.client, 'getPendingApprovals');
  }

  async startExecution(
    workflowId: string,
    versionHash: string,
    input: any
  ): Promise<string> {
    const resp = await this.startExecutionRpc({
      workflowId,
      versionHash,
      inputJson: JSON.stringify(input),
    });
    return resp.executionId;
  }

  async getStatus(
    executionId: string
  ): Promise<{ status: string; completedNodes: Record<string, any> }> {
    const resp = await this.getStatusRpc({ executionId });
    let completedNodes: Record<string, any> = {};
    try {
      completedNodes = JSON.parse(resp.completedNodesJson || '{}');
    } catch {}
    return {
      status: resp.status,
      completedNodes,
    };
  }

  async listExecutions(options?: {
    workflowId?: string;
    status?: string;
    limit?: number;
  }): Promise<ExecutionSummary[]> {
    const resp = await this.listExecutionsRpc({
      workflowId: options?.workflowId ?? '',
      status: options?.status ?? '',
      limit: options?.limit ?? 20,
    });
    return (resp.executions || []).map((e: any) => ({
      executionId: e.executionId,
      workflowId: e.workflowId,
      versionHash: e.versionHash,
      status: e.status,
      createdAt: e.createdAt,
    }));
  }

  async cancelExecution(executionId: string): Promise<void> {
    await this.cancelExecutionRpc({ executionId });
  }

  async listWorkflowVersions(workflowId: string): Promise<VersionInfo[]> {
    const resp = await this.listWorkflowVersionsRpc({ workflowId });
    return (resp.versions || []).map((v: any) => ({
      workflowId: v.workflowId,
      versionHash: v.versionHash,
      compatibility: v.compatibility,
      registeredAt: v.registeredAt,
      activeExecutions: v.activeExecutions ?? 0,
    }));
  }

  async approveTask(executionId: string, nodeId: string, approver: string, comment = ''): Promise<void> {
    await this.approveTaskRpc({ executionId, nodeId, approver, comment });
  }

  async rejectTask(executionId: string, nodeId: string, approver: string, reason: string): Promise<void> {
    await this.rejectTaskRpc({ executionId, nodeId, approver, reason });
  }

  async getPendingApprovals(): Promise<PendingApproval[]> {
    const resp = await this.getPendingApprovalsRpc({});
    return (resp.items || []).map((item: any) => ({
      executionId: item.executionId,
      nodeId: item.nodeId,
      workflowId: item.workflowId,
      startedAt: item.startedAt,
    }));
  }
}
