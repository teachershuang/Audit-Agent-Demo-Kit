import { create } from "zustand";
import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type { AnalysisTab, ContractAnalysisResult, ContractTask, EvidenceRef } from "../types/contract";
import type { RelationConfig } from "../types/relation";
import { api, postFrontendLog } from "../services/api";

type ActiveEntity =
  | { kind: "section"; id: string }
  | { kind: "clause"; id: string }
  | { kind: "audit"; id: string }
  | { kind: "relation"; id: string }
  | { kind: "verification"; id: string }
  | null;

interface ContractState {
  task: ContractTask | null;
  result: ContractAnalysisResult | null;
  relations: RelationConfig[];
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
  activeTab: AnalysisTab;
  activePage: number;
  selectedEvidenceId: string | null;
  activeEntity: ActiveEntity;
  isBusy: boolean;
  error: string | null;
  boot: () => Promise<void>;
  loadSample: () => Promise<void>;
  uploadAndAnalyze: (file?: File) => Promise<void>;
  reanalyze: () => Promise<void>;
  exportResult: () => void;
  setActiveTab: (tab: AnalysisTab) => void;
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

async function sleep(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

export const useContractStore = create<ContractState>((set, get) => ({
  result: null,
  task: null,
  relations: [],
  auditFocuses: [],
  verificationItems: [],
  agentSteps: [],
  activeTab: "sections",
  activePage: 1,
  selectedEvidenceId: null,
  activeEntity: null,
  isBusy: false,
  error: null,

  async boot() {
    try {
      const relations = await api.getRelations();
      set({ relations, error: null });
      await postFrontendLog("boot_completed", undefined, { relationCount: relations.length });
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

    const pollTask = async () => {
      if (!taskId) return null;
      while (true) {
        try {
          const task = await api.getContractTask(taskId);
          set({ task });
          if (task.status !== "processing") {
            return task;
          }
        } catch {
          // Ignore transient polling failures while the analysis is still active.
        }
        await sleep(1500);
      }
    };

    try {
      set({
        isBusy: true,
        error: null,
        result: null,
        auditFocuses: [],
        verificationItems: [],
        agentSteps: [],
      });

      taskId = await api.uploadContract(file);
      const initialTask = await api.getContractTask(taskId);
      set({ task: initialTask });

      const analyzePayload = await api.analyzeContract(taskId);
      const finalTask = await pollTask();
      if (!finalTask) {
        throw new Error("未能获取解析任务状态。");
      }
      if (finalTask.currentStage === "analysis_failed") {
        throw new Error(finalTask.stageDetail ?? "解析任务失败。");
      }

      const result = await api.getContractResult(taskId);
      const finalArtifacts = await api.analyzeContract(taskId);
      const relations = await api.getRelations();
      const selectedEvidenceId = result.sections[0]?.evidenceId ?? result.pages[0]?.evidences[0]?.id ?? null;

      set({
        task: result.task,
        result,
        relations,
        auditFocuses: finalArtifacts.auditFocuses ?? analyzePayload.auditFocuses ?? [],
        verificationItems: finalArtifacts.verificationItems ?? analyzePayload.verificationItems ?? [],
        agentSteps: finalArtifacts.agentSteps ?? analyzePayload.agentSteps ?? [],
        activeTab: "sections",
        activePage: result.pages[0]?.page ?? 1,
        selectedEvidenceId,
        activeEntity: result.sections[0] ? { kind: "section", id: result.sections[0].id } : null,
      });

      await postFrontendLog("upload_and_analyze_completed", undefined, {
        taskId,
        sections: result.sections.length,
        clauses: result.clauses.length,
        pages: result.pages.length,
      });
    } catch (error) {
      if (taskId) {
        try {
          const failedTask = await api.getContractTask(taskId);
          set({ task: failedTask });
        } catch {
          // Keep the last visible task state if task polling also fails.
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

    const pollTask = async () => {
      while (true) {
        try {
          const task = await api.getContractTask(currentTask.taskId);
          set({ task });
          if (task.status !== "processing") {
            return task;
          }
        } catch {
          // Ignore transient polling failures while the analysis is still active.
        }
        await sleep(1500);
      }
    };

    try {
      set({ isBusy: true, error: null });
      const analyzePayload = await api.analyzeContract(currentTask.taskId);
      const finalTask = await pollTask();
      if (!finalTask) {
        throw new Error("未能获取解析任务状态。");
      }
      if (finalTask.currentStage === "analysis_failed") {
        throw new Error(finalTask.stageDetail ?? "解析任务失败。");
      }
      const result = await api.getContractResult(currentTask.taskId);
      const finalArtifacts = await api.analyzeContract(currentTask.taskId);
      const relations = await api.getRelations();
      set({
        task: result.task,
        result,
        relations,
        auditFocuses: finalArtifacts.auditFocuses ?? analyzePayload.auditFocuses ?? [],
        verificationItems: finalArtifacts.verificationItems ?? analyzePayload.verificationItems ?? [],
        agentSteps: finalArtifacts.agentSteps ?? analyzePayload.agentSteps ?? [],
        activeTab: "sections",
        activePage: result.pages[0]?.page ?? 1,
        selectedEvidenceId: result.sections[0]?.evidenceId ?? result.pages[0]?.evidences[0]?.id ?? null,
        activeEntity: result.sections[0] ? { kind: "section", id: result.sections[0].id } : null,
      });
      await postFrontendLog("reanalyze_completed", undefined, { taskId: currentTask.taskId });
    } catch (error) {
      try {
        const failedTask = await api.getContractTask(currentTask.taskId);
        set({ task: failedTask });
      } catch {
        // Keep the last visible task state if task polling also fails.
      }
      const message = error instanceof Error ? error.message : "重新解析失败";
      await postFrontendLog("reanalyze_failed", message, { taskId: currentTask.taskId }, "error");
      set({ error: message });
    } finally {
      set({ isBusy: false });
    }
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

  focusEvidence(evidenceId, tab, entity) {
    const result = get().result;
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
