import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type { ContractAnalysisResult } from "../types/contract";
import type { RelationConfig } from "../types/relation";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

interface UploadResponse {
  task_id: string;
}

interface AnalyzeResponse {
  task_id: string;
  status: string;
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
}

async function safeJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as T;
}

export const api = {
  async uploadContract(file?: File): Promise<string> {
    const formData = new FormData();
    if (file) {
      formData.append("file", file);
    }
    formData.append("use_builtin_example", file ? "false" : "true");

    const response = await fetch(`${API_BASE_URL}/api/contracts/upload`, {
      method: "POST",
      body: formData,
    });
    const data = await safeJson<UploadResponse>(response);
    return data.task_id;
  },

  async analyzeContract(taskId: string): Promise<AnalyzeResponse> {
    const response = await fetch(`${API_BASE_URL}/api/contracts/${taskId}/analyze`, {
      method: "POST",
    });
    return await safeJson<AnalyzeResponse>(response);
  },

  async getContractResult(taskId: string): Promise<ContractAnalysisResult> {
    const response = await fetch(`${API_BASE_URL}/api/contracts/${taskId}/result`);
    return await safeJson<ContractAnalysisResult>(response);
  },

  async getRelations(): Promise<RelationConfig[]> {
    const response = await fetch(`${API_BASE_URL}/api/config/relations`);
    return await safeJson<RelationConfig[]>(response);
  },

  async createRelation(payload: RelationConfig): Promise<RelationConfig> {
    const response = await fetch(`${API_BASE_URL}/api/config/relations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await safeJson<RelationConfig>(response);
  },

  async updateRelation(relationId: string, payload: RelationConfig): Promise<RelationConfig> {
    const response = await fetch(`${API_BASE_URL}/api/config/relations/${relationId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await safeJson<RelationConfig>(response);
  },

  async deleteRelation(relationId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/config/relations/${relationId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      throw new Error(await response.text());
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
    const response = await fetch(`${API_BASE_URL}/api/audit/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, relations }),
    });
    return await safeJson(response);
  },
};
