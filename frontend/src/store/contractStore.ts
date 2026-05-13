import { create } from "zustand";
import type { AgentStep, AuditFocus, VerificationItem } from "../types/audit";
import type { AnalysisTab, ContractAnalysisResult, EvidenceRef } from "../types/contract";
import type { RelationConfig } from "../types/relation";
import { api } from "../services/api";

type ActiveEntity =
  | { kind: "section"; id: string }
  | { kind: "clause"; id: string }
  | { kind: "audit"; id: string }
  | { kind: "relation"; id: string }
  | { kind: "verification"; id: string }
  | null;

interface ContractState {
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

function deriveTabAndEntityFromEvidence(evidence: EvidenceRef): {
  tab: AnalysisTab;
  entity: ActiveEntity;
} {
  if (evidence.sourceType === "section") {
    return { tab: "sections", entity: { kind: "section", id: evidence.sourceId } };
  }

  return { tab: "clauses", entity: { kind: "clause", id: evidence.sourceId } };
}

export const useContractStore = create<ContractState>((set, get) => ({
  result: null,
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
    const relations = await api.getRelations();
    set({ relations });
  },

  async loadSample() {
    await get().uploadAndAnalyze();
  },

  async uploadAndAnalyze(file?: File) {
    try {
      set({ isBusy: true, error: null });
      const taskId = await api.uploadContract(file);
      await api.analyzeContract(taskId);
      const result = await api.getContractResult(taskId);
      const relations = await api.getRelations();
      const selectedEvidenceId =
        result.sections[0]?.evidenceId ?? result.pages[0]?.evidences[0]?.id ?? null;

      set({
        result,
        relations,
        auditFocuses: [],
        verificationItems: [],
        agentSteps: [],
        activeTab: "sections",
        activePage: result.pages[0]?.page ?? 1,
        selectedEvidenceId,
        activeEntity: result.sections[0] ? { kind: "section", id: result.sections[0].id } : null,
      });

      await get().regenerateAudit();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "加载失败" });
    } finally {
      set({ isBusy: false });
    }
  },

  async reanalyze() {
    const current = get().result;
    if (!current) return;

    await get().uploadAndAnalyze(new File(["mock"], current.task.fileName, { type: "application/pdf" }));
  },

  exportResult() {
    const { result, relations, auditFocuses, verificationItems, agentSteps } = get();
    if (!result) return;
    const blob = new Blob(
      [
        JSON.stringify(
          { result, relations, auditFocuses, verificationItems, agentSteps },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${result.task.taskId}-analysis.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  },

  setActiveTab(tab) {
    set({ activeTab: tab });
  },

  focusEvidence(evidenceId, tab, entity) {
    const result = get().result;
    if (!result) return;
    const matchedPage = result.pages.find((page) =>
      page.evidences.some((evidence) => evidence.id === evidenceId),
    );
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
    const saved = exists
      ? await api.updateRelation(relation.id, relation)
      : await api.createRelation(relation);

    set({
      relations: exists
        ? get().relations.map((item) => (item.id === relation.id ? saved : item))
        : [...get().relations, saved],
      activeEntity: { kind: "relation", id: saved.id },
      activeTab: "relations",
    });
  },

  async removeRelation(relationId) {
    await api.deleteRelation(relationId);
    const activeEntity = get().activeEntity;
    set({
      relations: get().relations.filter((item) => item.id !== relationId),
      activeEntity:
        activeEntity?.kind === "relation" && activeEntity.id === relationId ? null : activeEntity,
    });
  },

  async regenerateAudit() {
    const result = get().result;
    if (!result) return;

    set({ isBusy: true });
    try {
      const payload = await api.generateAudit(result.task.taskId, get().relations);
      set({
        auditFocuses: payload.auditFocuses,
        verificationItems: payload.verificationItems,
        agentSteps: payload.agentSteps,
      });
    } finally {
      set({ isBusy: false });
    }
  },
}));
