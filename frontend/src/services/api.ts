import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type {
  ApiHealth,
  BaseClauseRecord,
  BaseClauseMetadata,
  BaseContractSchema,
  BaseDocumentMetadata,
  BaseDocumentRecord,
  BaseReviewReport,
  BaseReviewTask,
  BaseRuleMetadata,
  BaseRuleRecord,
  RuntimeModelProfileState,
  SourceTaskSummary,
} from "../types/base";
import type { ContractAnalysisResult, ContractTask } from "../types/contract";
import type { RelationConfig } from "../types/relation";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;

const candidateBaseUrls = () => {
  const host = window.location.hostname || "127.0.0.1";
  return [`http://${host}:8010`, configuredBaseUrl, `http://${host}:8000`].filter(
    (value): value is string => Boolean(value),
  );
};

let cachedApiBaseUrl: string | null = null;
let cachedHealth: ApiHealth | null = null;

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

interface BaseUploadResponse {
  document: BaseDocumentRecord;
  clause_count: number;
  rule_count: number;
  rules: BaseRuleRecord[];
}

async function detectApiBaseUrl(): Promise<string> {
  if (cachedApiBaseUrl) return cachedApiBaseUrl;

  for (const baseUrl of candidateBaseUrls()) {
    try {
      const response = await fetch(`${baseUrl}/health`, { method: "GET" });
      if (!response.ok) continue;
      const payload = (await response.json()) as ApiHealth;
      if (payload.status === "ok") {
        cachedApiBaseUrl = baseUrl;
        cachedHealth = payload;
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
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: string };
      throw new Error(payload.detail || `Request failed with status ${response.status}`);
    }
    throw new Error((await response.text()) || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

function summarizeForLog(value: unknown): unknown {
  if (value == null) return value;
  if (value instanceof FormData) {
    const entries: Array<Record<string, unknown>> = [];
    value.forEach((entryValue, key) => {
      if (entryValue instanceof File) {
        entries.push({
          key,
          fileName: entryValue.name,
          type: entryValue.type,
          size: entryValue.size,
        });
      } else {
        entries.push({ key, value: String(entryValue) });
      }
    });
    return { kind: "FormData", entries };
  }
  if (typeof value === "string") {
    return value.length > 2400 ? `${value.slice(0, 2400)} ... [truncated ${value.length - 2400} chars]` : value;
  }
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.slice(0, 40).map((item) => summarizeForLog(item));
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, entryValue]) => [key, summarizeForLog(entryValue)]),
    );
  }
  return String(value);
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
  const method = init?.method ?? "GET";
  const started = performance.now();
  const requestPayload = summarizeForLog(init?.body ?? null);
  await postFrontendLog("api_request_started", undefined, { method, path, request: requestPayload }, "debug");
  try {
    const response = await fetch(`${baseUrl}${path}`, init);
    const payload = await safeJson<T>(response);
    await postFrontendLog(
      "api_request_completed",
      undefined,
      {
        method,
        path,
        status: response.status,
        durationMs: Math.round(performance.now() - started),
        response: summarizeForLog(payload),
      },
      "debug",
    );
    return payload;
  } catch (error) {
    await postFrontendLog(
      "api_request_failed",
      error instanceof Error ? error.message : "unknown error",
      {
        method,
        path,
        durationMs: Math.round(performance.now() - started),
        request: requestPayload,
      },
      "error",
    );
    if (error instanceof TypeError) {
      throw new Error("无法连接解析服务，请检查后端是否仍在运行。");
    }
    throw error;
  }
}

export async function postFrontendLog(
  event: string,
  message?: string,
  context?: Record<string, unknown>,
  level = "info",
) {
  const payload = { level, event, message, context: context ?? {} };

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
  async getHealth(forceRefresh = false): Promise<ApiHealth> {
    if (cachedHealth && !forceRefresh) {
      return cachedHealth;
    }
    const baseUrl = await detectApiBaseUrl();
    const response = await fetch(`${baseUrl}/health`);
    const payload = await safeJson<ApiHealth>(response);
    cachedHealth = payload;
    return payload;
  },

  async getRuntimeModelProfiles(): Promise<RuntimeModelProfileState> {
    return await request<RuntimeModelProfileState>("/api/runtime/model-profiles");
  },

  async switchRuntimeModelProfile(profileId: string): Promise<RuntimeModelProfileState> {
    const payload = await request<RuntimeModelProfileState>("/api/runtime/model-profiles/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId }),
    });
    cachedHealth = null;
    return payload;
  },

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

    const data = await request<UploadResponse>("/api/contracts/upload", { method: "POST", body: formData });
    await postFrontendLog("upload_contract_completed", undefined, { taskId: data.task_id });
    return data.task_id;
  },

  async analyzeContract(taskId: string): Promise<AnalyzeResponse> {
    await postFrontendLog("analyze_contract_started", undefined, { taskId });
    const data = await request<AnalyzeResponse>(`/api/contracts/${taskId}/analyze`, { method: "POST" });
    const normalized = normalizeAnalyzeResponse(data);
    await postFrontendLog("analyze_contract_completed", undefined, {
      taskId,
      auditFocuses: normalized.auditFocuses?.length ?? 0,
      verificationItems: normalized.verificationItems?.length ?? 0,
      agentSteps: normalized.agentSteps?.length ?? 0,
    });
    return normalized;
  },

  async getContractTask(taskId: string): Promise<ContractTask> {
    return await request<ContractTask>(`/api/contracts/${taskId}`);
  },

  async getContractResult(taskId: string): Promise<ContractAnalysisResult> {
    return await request<ContractAnalysisResult>(`/api/contracts/${taskId}/result`);
  },

  async reanalyzeFromResult(taskId: string, payload: ContractAnalysisResult): Promise<{ task_id: string; status: string; message: string }> {
    return await request<{ task_id: string; status: string; message: string }>(`/api/contracts/${taskId}/reanalyze-from-result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
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
    const response = await fetch(`${baseUrl}/api/config/relations/${relationId}`, { method: "DELETE" });
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

  async getLogFile(path: string): Promise<{ path: string; content: string }> {
    const encoded = encodeURIComponent(path);
    return await request<{ path: string; content: string }>(`/api/logs/file?path=${encoded}`);
  },

  base: {
    async uploadDocument(payload: {
      file: File;
      docType: string;
      version: string;
      issuer: string;
      category: string;
      effectiveTs: number;
    }): Promise<{ document: BaseDocumentRecord; clauseCount: number; rules: BaseRuleRecord[] }> {
      const formData = new FormData();
      formData.append("file", payload.file);
      formData.append("doc_type", payload.docType);
      formData.append("version", payload.version);
      formData.append("issuer", payload.issuer);
      formData.append("category", payload.category);
      formData.append("effective_ts", String(payload.effectiveTs));
      const data = await request<BaseUploadResponse>("/api/base/documents/upload", { method: "POST", body: formData });
      return {
        document: data.document,
        clauseCount: data.clause_count,
        rules: data.rules,
      };
    },

    async listDocuments(): Promise<BaseDocumentRecord[]> {
      return await request<BaseDocumentRecord[]>("/api/base/documents");
    },

    async getDocumentMetadata(docId: string, includeClauses = false): Promise<BaseDocumentMetadata> {
      return await request<BaseDocumentMetadata>(`/api/base/documents/${docId}/metadata?include_clauses=${includeClauses ? "true" : "false"}`);
    },

    async getDocumentClauses(docId: string): Promise<BaseClauseRecord[]> {
      return await request<BaseClauseRecord[]>(`/api/base/documents/${docId}/clauses`);
    },

    async patchDocument(docId: string, payload: Record<string, unknown>): Promise<BaseDocumentRecord> {
      return await request<BaseDocumentRecord>(`/api/base/documents/${docId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    async getClauseMetadata(clauseId: string): Promise<BaseClauseMetadata> {
      return await request<BaseClauseMetadata>(`/api/base/documents/clauses/${clauseId}`);
    },

    async abolishDocument(docId: string): Promise<void> {
      await request(`/api/base/documents/${docId}/abolish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
    },

    async replaceDocument(oldDocId: string, newDocId: string): Promise<void> {
      await request(`/api/base/documents/${oldDocId}/replace/${newDocId}`, { method: "POST" });
    },

    async listRules(): Promise<BaseRuleRecord[]> {
      return await request<BaseRuleRecord[]>("/api/base/rules");
    },

    async getRule(ruleId: string): Promise<BaseRuleRecord> {
      return await request<BaseRuleRecord>(`/api/base/rules/${ruleId}`);
    },

    async getRuleMetadata(ruleId: string): Promise<BaseRuleMetadata> {
      return await request<BaseRuleMetadata>(`/api/base/rules/${ruleId}/metadata`);
    },

    async patchRule(ruleId: string, payload: Record<string, unknown>): Promise<BaseRuleRecord> {
      return await request<BaseRuleRecord>(`/api/base/rules/${ruleId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    async listSourceTasks(): Promise<SourceTaskSummary[]> {
      return await request<SourceTaskSummary[]>("/api/base/contracts/source-tasks");
    },

    async reviewContract(payload: { sourceTaskId: string; selectedTemplateId: string }): Promise<{
      contract_id: string;
      issue_count: number;
      detected_category: string;
      status: string;
    }> {
      return await request("/api/base/contracts/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_task_id: payload.sourceTaskId,
          selected_template_id: payload.selectedTemplateId || null,
        }),
      });
    },

    async startReviewContract(payload: { sourceTaskId: string; selectedTemplateId: string }): Promise<BaseReviewTask> {
      return await request<BaseReviewTask>("/api/base/contracts/review/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_task_id: payload.sourceTaskId,
          selected_template_id: payload.selectedTemplateId || null,
        }),
      });
    },

    async getReviewTask(taskId: string): Promise<BaseReviewTask> {
      return await request<BaseReviewTask>(`/api/base/contracts/review-tasks/${taskId}`);
    },

    async getContractSchema(contractId: string): Promise<BaseContractSchema> {
      return await request<BaseContractSchema>(`/api/base/contracts/${contractId}/schema`);
    },

    async getContractReport(contractId: string): Promise<BaseReviewReport> {
      return await request<BaseReviewReport>(`/api/base/contracts/${contractId}/report`);
    },
  },
};
