import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type { ContractAnalysisResult } from "../types/contract";
import type { RelationConfig } from "../types/relation";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;

const candidateBaseUrls = () => {
  const host = window.location.hostname || "127.0.0.1";
  return [`http://${host}:8010`, configuredBaseUrl, `http://${host}:8000`].filter(
    (value): value is string => Boolean(value),
  );
};

let cachedApiBaseUrl: string | null = null;

interface UploadResponse {
  task_id: string;
}

interface AnalyzeResponse {
  task_id: string;
  status: string;
  auditFocuses?: AuditFocus[];
  verificationItems?: VerificationItem[];
  agentSteps?: AgentStep[];
}

async function detectApiBaseUrl(): Promise<string> {
  if (cachedApiBaseUrl) return cachedApiBaseUrl;

  for (const baseUrl of candidateBaseUrls()) {
    try {
      const response = await fetch(`${baseUrl}/health`, { method: "GET" });
      if (!response.ok) continue;
      const payload = (await response.json()) as { status?: string };
      if (payload.status === "ok") {
        cachedApiBaseUrl = baseUrl;
        return baseUrl;
      }
    } catch {
      continue;
    }
  }

  const fallback = configuredBaseUrl ?? "http://127.0.0.1:8010";
  cachedApiBaseUrl = fallback;
  return fallback;
}

export function getApiBaseUrlSync(): string {
  return cachedApiBaseUrl ?? candidateBaseUrls()[0] ?? "http://127.0.0.1:8010";
}

async function safeJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as T;
}

function normalizeAnalyzeResponse(data: AnalyzeResponse): AnalyzeResponse {
  return {
    ...data,
    auditFocuses: data.auditFocuses ?? [],
    verificationItems: data.verificationItems ?? [],
    agentSteps: data.agentSteps ?? [],
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = await detectApiBaseUrl();
  const response = await fetch(`${baseUrl}${path}`, init);
  return await safeJson<T>(response);
}

export async function postFrontendLog(
  event: string,
  message?: string,
  context?: Record<string, unknown>,
  level = "info",
) {
  const payload = {
    level,
    event,
    message,
    context: context ?? {},
  };

  try {
    const baseUrl = await detectApiBaseUrl();
    await fetch(`${baseUrl}/api/logs/frontend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    console[level === "error" ? "error" : "log"]("[frontend-log]", payload);
  }
}

export const api = {
  async uploadContract(file?: File): Promise<string> {
    const formData = new FormData();
    if (file) {
      formData.append("file", file);
    }
    formData.append("use_builtin_example", file ? "false" : "true");

    await postFrontendLog("upload_contract_clicked", file ? "user-selected-file" : "load-builtin-example", {
      fileName: file?.name ?? null,
      size: file?.size ?? null,
      type: file?.type ?? null,
    });

    const data = await request<UploadResponse>("/api/contracts/upload", {
      method: "POST",
      body: formData,
    });
    await postFrontendLog("upload_contract_completed", undefined, { taskId: data.task_id });
    return data.task_id;
  },

  async analyzeContract(taskId: string): Promise<AnalyzeResponse> {
    await postFrontendLog("analyze_contract_started", undefined, { taskId });
    const data = await request<AnalyzeResponse>(`/api/contracts/${taskId}/analyze`, {
      method: "POST",
    });
    const normalized = normalizeAnalyzeResponse(data);
    await postFrontendLog("analyze_contract_completed", undefined, {
      taskId,
      auditFocuses: normalized.auditFocuses?.length ?? 0,
      verificationItems: normalized.verificationItems?.length ?? 0,
      agentSteps: normalized.agentSteps?.length ?? 0,
    });
    return normalized;
  },

  async getContractResult(taskId: string): Promise<ContractAnalysisResult> {
    return await request<ContractAnalysisResult>(`/api/contracts/${taskId}/result`);
  },

  async getRelations(): Promise<RelationConfig[]> {
    return await request<RelationConfig[]>("/api/config/relations");
  },

  async createRelation(payload: RelationConfig): Promise<RelationConfig> {
    return await request<RelationConfig>("/api/config/relations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  async updateRelation(relationId: string, payload: RelationConfig): Promise<RelationConfig> {
    return await request<RelationConfig>(`/api/config/relations/${relationId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  async deleteRelation(relationId: string): Promise<void> {
    const baseUrl = await detectApiBaseUrl();
    const response = await fetch(`${baseUrl}/api/config/relations/${relationId}`, {
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
    const data = await request<{
      auditFocuses?: AuditFocus[];
      verificationItems?: VerificationItem[];
      agentSteps?: AgentStep[];
    }>("/api/audit/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId, relations }),
    });
    return {
      auditFocuses: data.auditFocuses ?? [],
      verificationItems: data.verificationItems ?? [],
      agentSteps: data.agentSteps ?? [],
    };
  },
};
