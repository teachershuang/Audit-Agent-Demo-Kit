import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type { ContractAnalysisResult } from "../types/contract";
import type { RelationConfig } from "../types/relation";
import { createDemoPayload } from "./mockData";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

interface UploadResponse {
  task_id: string;
}

interface DemoState {
  taskId: string;
  result: ContractAnalysisResult;
  relations: RelationConfig[];
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
}

const localState: DemoState = (() => {
  const payload = createDemoPayload();
  return {
    taskId: payload.result.task.taskId,
    ...payload,
  };
})();

async function safeJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as T;
}

function refreshLocalState() {
  const payload = createDemoPayload();
  localState.result = payload.result;
  localState.relations = payload.relations;
  localState.auditFocuses = payload.auditFocuses;
  localState.verificationItems = payload.verificationItems;
  localState.agentSteps = payload.agentSteps;
}

export const api = {
  async uploadContract(file?: File): Promise<string> {
    try {
      const formData = new FormData();
      if (file) {
        formData.append("file", file);
      }
      formData.append("use_sample", file ? "false" : "true");

      const response = await fetch(`${API_BASE_URL}/api/contracts/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await safeJson<UploadResponse>(response);
      return data.task_id;
    } catch {
      refreshLocalState();
      return localState.taskId;
    }
  },

  async analyzeContract(taskId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/contracts/${taskId}/analyze`, {
        method: "POST",
      });
      await safeJson(response);
    } catch {
      localState.result.task.status = "needs_review";
    }
  },

  async getContractResult(taskId: string): Promise<ContractAnalysisResult> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/contracts/${taskId}/result`);
      return await safeJson<ContractAnalysisResult>(response);
    } catch {
      return structuredClone(localState.result);
    }
  },

  async getRelations(): Promise<RelationConfig[]> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/relations`);
      return await safeJson<RelationConfig[]>(response);
    } catch {
      return structuredClone(localState.relations);
    }
  },

  async createRelation(payload: RelationConfig): Promise<RelationConfig> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/relations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return await safeJson<RelationConfig>(response);
    } catch {
      localState.relations = [...localState.relations, payload];
      return payload;
    }
  },

  async updateRelation(relationId: string, payload: RelationConfig): Promise<RelationConfig> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/relations/${relationId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return await safeJson<RelationConfig>(response);
    } catch {
      localState.relations = localState.relations.map((item) =>
        item.id === relationId ? payload : item,
      );
      return payload;
    }
  },

  async deleteRelation(relationId: string): Promise<void> {
    try {
      await fetch(`${API_BASE_URL}/api/config/relations/${relationId}`, {
        method: "DELETE",
      });
    } catch {
      localState.relations = localState.relations.filter((item) => item.id !== relationId);
    }
  },

  async generateAudit(
    taskId: string,
    relations: RelationConfig[],
  ): Promise<{
    auditFocuses: AuditFocus[];
    verificationItems: VerificationItem[];
    agentSteps: AgentStep[];
  }> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/audit/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId, relations }),
      });
      return await safeJson(response);
    } catch {
      localState.relations = relations;
      return {
        auditFocuses: structuredClone(localState.auditFocuses),
        verificationItems: structuredClone(localState.verificationItems),
        agentSteps: structuredClone(localState.agentSteps),
      };
    }
  },
};
