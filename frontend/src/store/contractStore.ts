import { create } from "zustand";
import { api, postFrontendLog } from "../services/api";
import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type { ApiHealth } from "../types/base";
import type { AnalysisTab, ContractAnalysisResult, ContractTask, EvidenceRef } from "../types/contract";
import type { RelationConfig } from "../types/relation";

type ActiveEntity =
  | { kind: "section"; id: string }
  | { kind: "clause"; id: string }
  | { kind: "audit"; id: string }
  | { kind: "relation"; id: string }
  | { kind: "verification"; id: string }
  | null;

interface ClauseDraftFieldPatch {
  clauseId: string;
  fieldKey: string;
  value: unknown;
}

interface ContractState {
  task: ContractTask | null;
  result: ContractAnalysisResult | null;
  draftResult: ContractAnalysisResult | null;
  lastDraftSnapshot: ContractAnalysisResult | null;
  relations: RelationConfig[];
  health: ApiHealth | null;
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
  activeTab: AnalysisTab;
  activePage: number;
  selectedEvidenceId: string | null;
  activeEntity: ActiveEntity;
  isBusy: boolean;
  error: string | null;
  isEditMode: boolean;
  hasUnsavedDraft: boolean;
  boot: () => Promise<void>;
  loadSample: () => Promise<void>;
  uploadAndAnalyze: (file?: File) => Promise<void>;
  reanalyze: () => Promise<void>;
  saveDraftAndReanalyze: () => Promise<void>;
  undoDraft: () => void;
  discardDraft: () => void;
  setEditMode: (enabled: boolean) => void;
  updateClauseStructuredField: (patch: ClauseDraftFieldPatch) => void;
  exportResult: () => void;
  setActiveTab: (tab: AnalysisTab) => void;
  setActivePage: (page: number) => void;
  focusEvidence: (evidenceId: string, tab: AnalysisTab, entity: ActiveEntity) => void;
  focusFromEvidence: (evidence: EvidenceRef) => void;
  saveRelation: (relation: RelationConfig) => Promise<void>;
  removeRelation: (relationId: string) => Promise<void>;
  regenerateAudit: () => Promise<void>;
}

function deriveTabAndEntityFromEvidence(evidence: EvidenceRef): { tab: AnalysisTab; entity: ActiveEntity } {
  if (evidence.sourceType === "section") {
    return { tab: "sections", entity: { kind: "section", id: evidence.sourceId } };
  }
  return { tab: "clauses", entity: { kind: "clause", id: evidence.sourceId } };
}

function cloneResult(result: ContractAnalysisResult | null): ContractAnalysisResult | null {
  return result ? structuredClone(result) : null;
}

function pickInitialEvidence(result: ContractAnalysisResult) {
  return result.sections[0]?.evidenceId ?? result.pages[0]?.evidences[0]?.id ?? null;
}

function pickInitialEntity(result: ContractAnalysisResult): ActiveEntity {
  return result.sections[0] ? { kind: "section", id: result.sections[0].id } : null;
}

async function sleep(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitForTaskCompletion(taskId: string, onTask: (task: ContractTask) => void): Promise<ContractTask> {
  const deadline = Date.now() + 15 * 60 * 1000;
  while (true) {
    try {
      const task = await api.getContractTask(taskId);
      onTask(task);
      if (task.status !== "processing") {
        return task;
      }
      if (Date.now() > deadline) {
        throw new Error(`解析等待超时。当前阶段：${task.stageDetail ?? task.currentStage ?? "处理中"}`);
      }
    } catch (error) {
      if (Date.now() > deadline) {
        throw error instanceof Error ? error : new Error("解析等待超时。");
      }
    }
    await sleep(1500);
  }
}

async function waitForKnowledgeBaseCompletion(taskId: string, onTask: (task: ContractTask) => void): Promise<ContractTask> {
  const deadline = Date.now() + 30 * 60 * 1000;
  while (true) {
    const task = await api.getContractTask(taskId);
    onTask(task);
    if (task.currentStage !== "knowledge_base_review" || task.progressPercent >= 100) {
      return task;
    }
    if (Date.now() > deadline) {
      throw new Error("制度底座校验等待超时。");
    }
    await sleep(3000);
  }
}

async function loadTaskArtifacts(taskId: string) {
  const [result, finalArtifacts, relations, health] = await Promise.all([
    api.getContractResult(taskId),
    api.analyzeContract(taskId),
    api.getRelations(),
    api.getHealth(),
  ]);
  return { result, finalArtifacts, relations, health };
}

function applyLoadedResult(
  set: (partial: Partial<ContractState>) => void,
  payload: Awaited<ReturnType<typeof loadTaskArtifacts>>,
  preferredTab?: AnalysisTab,
) {
  const selectedEvidenceId = pickInitialEvidence(payload.result);
  set({
    task: payload.result.task,
    result: payload.result,
    draftResult: cloneResult(payload.result),
    lastDraftSnapshot: null,
    relations: payload.relations,
    health: payload.health,
    auditFocuses: payload.finalArtifacts.auditFocuses ?? [],
    verificationItems: payload.finalArtifacts.verificationItems ?? [],
    agentSteps: payload.finalArtifacts.agentSteps ?? [],
    activeTab: preferredTab ?? (payload.result.task.currentStage === "knowledge_base_review" ? "knowledge" : "sections"),
    activePage: payload.result.pages[0]?.page ?? 1,
    selectedEvidenceId,
    activeEntity: pickInitialEntity(payload.result),
    hasUnsavedDraft: false,
    isEditMode: false,
  });
}

export const useContractStore = create<ContractState>((set, get) => ({
  result: null,
  draftResult: null,
  lastDraftSnapshot: null,
  task: null,
  relations: [],
  health: null,
  auditFocuses: [],
  verificationItems: [],
  agentSteps: [],
  activeTab: "sections",
  activePage: 1,
  selectedEvidenceId: null,
  activeEntity: null,
  isBusy: false,
  error: null,
  isEditMode: false,
  hasUnsavedDraft: false,

  async boot() {
    try {
      const [relations, health] = await Promise.all([api.getRelations(), api.getHealth(true)]);
      set({ relations, health, error: null });
      await postFrontendLog("boot_completed", undefined, {
        relationCount: relations.length,
        textModel: health.text_model,
        visionModel: health.vision_model,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "服务连接失败";
      await postFrontendLog("boot_failed", message, {}, "error");
      set({ error: message });
    }
  },

  async loadSample() {
    await postFrontendLog("load_sample_clicked");
    await get().uploadAndAnalyze();
  },

  async uploadAndAnalyze(file?: File) {
    let taskId: string | null = null;
    try {
      set({
        isBusy: true,
        error: null,
        result: null,
        draftResult: null,
        auditFocuses: [],
        verificationItems: [],
        agentSteps: [],
      });
      taskId = await api.uploadContract(file);
      const initialTask = await api.getContractTask(taskId);
      set({ task: initialTask });
      const analyzePayload = await api.analyzeContract(taskId);
      const finalTask =
        analyzePayload.status === "processing"
          ? await waitForTaskCompletion(taskId, (task) => set({ task }))
          : await api.getContractTask(taskId);
      if (finalTask.currentStage === "analysis_failed") {
        throw new Error(finalTask.stageDetail ?? "解析任务失败。");
      }
      const payload = await loadTaskArtifacts(taskId);
      applyLoadedResult(set, payload);
      if (payload.result.task.currentStage === "knowledge_base_review") {
        void (async () => {
          try {
            await waitForKnowledgeBaseCompletion(taskId!, (task) => set({ task }));
            const merged = await loadTaskArtifacts(taskId!);
            applyLoadedResult(set, merged, "knowledge");
          } catch (error) {
            set({ error: error instanceof Error ? error.message : "制度底座校验刷新失败" });
          }
        })();
      }
      await postFrontendLog("upload_and_analyze_completed", undefined, {
        taskId,
        sections: payload.result.sections.length,
        clauses: payload.result.clauses.length,
        pages: payload.result.pages.length,
      });
    } catch (error) {
      if (taskId) {
        try {
          set({ task: await api.getContractTask(taskId) });
        } catch {
          // Keep last visible task state.
        }
      }
      const message = error instanceof Error ? error.message : "加载失败";
      await postFrontendLog(
        "upload_and_analyze_failed",
        message,
        { fileName: file?.name ?? null, size: file?.size ?? null },
        "error",
      );
      set({ error: message });
    } finally {
      set({ isBusy: false });
    }
  },

  async reanalyze() {
    const currentTask = get().task ?? get().result?.task ?? null;
    if (!currentTask) return;
    try {
      set({ isBusy: true, error: null });
      const analyzePayload = await api.analyzeContract(currentTask.taskId);
      const finalTask =
        analyzePayload.status === "processing"
          ? await waitForTaskCompletion(currentTask.taskId, (task) => set({ task }))
          : await api.getContractTask(currentTask.taskId);
      if (finalTask.currentStage === "analysis_failed") {
        throw new Error(finalTask.stageDetail ?? "解析任务失败。");
      }
      const payload = await loadTaskArtifacts(currentTask.taskId);
      applyLoadedResult(set, payload);
      if (payload.result.task.currentStage === "knowledge_base_review") {
        void (async () => {
          try {
            await waitForKnowledgeBaseCompletion(currentTask.taskId, (task) => set({ task }));
            const merged = await loadTaskArtifacts(currentTask.taskId);
            applyLoadedResult(set, merged, "knowledge");
          } catch (error) {
            set({ error: error instanceof Error ? error.message : "制度底座校验刷新失败" });
          }
        })();
      }
      await postFrontendLog("reanalyze_completed", undefined, { taskId: currentTask.taskId });
    } catch (error) {
      try {
        set({ task: await api.getContractTask(currentTask.taskId) });
      } catch {
        // Keep last visible task state.
      }
      const message = error instanceof Error ? error.message : "重新解析失败";
      await postFrontendLog("reanalyze_failed", message, { taskId: currentTask.taskId }, "error");
      set({ error: message });
    } finally {
      set({ isBusy: false });
    }
  },

  async saveDraftAndReanalyze() {
    const { draftResult, task } = get();
    if (!draftResult || !task) return;
    try {
      set({ isBusy: true, error: null });
      await api.reanalyzeFromResult(task.taskId, draftResult);
      await waitForTaskCompletion(task.taskId, (nextTask) => set({ task: nextTask }));
      const payload = await loadTaskArtifacts(task.taskId);
      applyLoadedResult(set, payload, "clauses");
      if (payload.result.task.currentStage === "knowledge_base_review") {
        void (async () => {
          try {
            await waitForKnowledgeBaseCompletion(task.taskId, (nextTask) => set({ task: nextTask }));
            const merged = await loadTaskArtifacts(task.taskId);
            applyLoadedResult(set, merged, "knowledge");
          } catch (error) {
            set({ error: error instanceof Error ? error.message : "制度底座校验刷新失败" });
          }
        })();
      }
      await postFrontendLog("save_draft_and_reanalyze_completed", undefined, { taskId: task.taskId });
    } catch (error) {
      const message = error instanceof Error ? error.message : "保存草稿并重审失败";
      await postFrontendLog("save_draft_and_reanalyze_failed", message, { taskId: task.taskId }, "error");
      set({ error: message });
    } finally {
      set({ isBusy: false });
    }
  },

  undoDraft() {
    const snapshot = get().lastDraftSnapshot;
    if (!snapshot) return;
    set({
      draftResult: cloneResult(snapshot),
      lastDraftSnapshot: null,
      hasUnsavedDraft: true,
    });
  },

  discardDraft() {
    set({
      draftResult: cloneResult(get().result),
      lastDraftSnapshot: null,
      hasUnsavedDraft: false,
      isEditMode: false,
    });
  },

  setEditMode(enabled) {
    set({ isEditMode: enabled });
  },

  updateClauseStructuredField({ clauseId, fieldKey, value }) {
    const draftResult = cloneResult(get().draftResult);
    if (!draftResult) return;
    const clause = draftResult.clauses.find((item) => item.id === clauseId);
    if (!clause) return;
    set({
      lastDraftSnapshot: cloneResult(get().draftResult),
    });
    const nextFields = { ...(clause.structuredFields ?? {}) };
    nextFields[fieldKey] = value;
    clause.structuredFields = nextFields;
    set({
      draftResult,
      hasUnsavedDraft: true,
    });
  },

  exportResult() {
    const { result, relations, auditFocuses, verificationItems, agentSteps } = get();
    if (!result) return;
    const blob = new Blob([JSON.stringify({ result, relations, auditFocuses, verificationItems, agentSteps }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${result.task.taskId}-analysis.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    void postFrontendLog("export_result_clicked", undefined, { taskId: result.task.taskId });
  },

  setActiveTab(tab) {
    set({ activeTab: tab });
  },

  setActivePage(page) {
    set({ activePage: page });
  },

  focusEvidence(evidenceId, tab, entity) {
    const result = get().draftResult ?? get().result;
    if (!result) return;
    const matchedPage = result.pages.find((page) => page.evidences.some((evidence) => evidence.id === evidenceId));
    set({
      selectedEvidenceId: evidenceId,
      activeTab: tab,
      activeEntity: entity,
      activePage: matchedPage?.page ?? get().activePage,
    });
  },

  focusFromEvidence(evidence) {
    const { tab, entity } = deriveTabAndEntityFromEvidence(evidence);
    set({
      selectedEvidenceId: evidence.id,
      activeTab: tab,
      activePage: evidence.page,
      activeEntity: entity,
    });
  },

  async saveRelation(relation) {
    const exists = get().relations.some((item) => item.id === relation.id);
    const saved = exists ? await api.updateRelation(relation.id, relation) : await api.createRelation(relation);
    set({
      relations: exists ? get().relations.map((item) => (item.id === relation.id ? saved : item)) : [...get().relations, saved],
      activeEntity: { kind: "relation", id: saved.id },
    });
  },

  async removeRelation(relationId) {
    await api.deleteRelation(relationId);
    const activeEntity = get().activeEntity;
    set({
      relations: get().relations.filter((item) => item.id !== relationId),
      activeEntity: activeEntity?.kind === "relation" && activeEntity.id === relationId ? null : activeEntity,
    });
  },

  async regenerateAudit() {
    const result = get().result;
    if (!result) return;
    set({ isBusy: true, error: null });
    try {
      const payload = await api.generateAudit(result.task.taskId, get().relations);
      set({
        auditFocuses: payload.auditFocuses ?? [],
        verificationItems: payload.verificationItems ?? [],
        agentSteps: payload.agentSteps ?? [],
      });
      await postFrontendLog("regenerate_audit_completed", undefined, { taskId: result.task.taskId });
    } catch (error) {
      const message = error instanceof Error ? error.message : "重新生成关注点失败";
      await postFrontendLog("regenerate_audit_failed", message, { taskId: result.task.taskId }, "error");
      set({ error: message });
    } finally {
      set({ isBusy: false });
    }
  },
}));
