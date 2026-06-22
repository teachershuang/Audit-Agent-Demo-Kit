import { useEffect, useMemo, useState } from "react";
import { useContractStore } from "../../store/contractStore";
import type { KeyFact } from "../../types/contract";
import { AnalysisTabs } from "../analysis/AnalysisTabs";
import { ContractViewer } from "../contract/ContractViewer";
import { RelationConfigPanel } from "../config/RelationConfigPanel";
import { AppShell } from "../layout/AppShell";
import { HeaderBar } from "../layout/HeaderBar";
import { EmptyState } from "../shared/EmptyState";
import { ErrorBanner } from "../shared/ErrorBanner";
import { LoadingState } from "../shared/LoadingState";

function deriveContractNumber(keyFacts: KeyFact[]): string | null {
  const fact = keyFacts.find((item) => item.label === "合同编号" || item.label === "协议编号");
  const value = fact?.value.trim();
  if (!value || value === "未提取" || value === "待提取") {
    return null;
  }
  return value;
}

function AuditConfigModal({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
      <div className="flex max-h-[88vh] w-full max-w-[1080px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[#0f1b2d] shadow-[0_30px_120px_rgba(2,8,23,0.55)]">
        <div className="flex items-center justify-between border-b border-white/8 px-5 py-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">Review Config</div>
            <h2 className="mt-1 text-xl font-semibold text-white">审计配置</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-200 hover:border-cyan-400/24 hover:bg-white/[0.06]"
          >
            关闭
          </button>
        </div>
        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

export function AnalysisWorkspace({ refreshToken = 0 }: { refreshToken?: number }) {
  const [auditConfigOpen, setAuditConfigOpen] = useState(false);
  const {
    task,
    result,
    draftResult,
    relations,
    health,
    auditFocuses,
    verificationItems,
    agentSteps,
    activeTab,
    activePage,
    activeEntity,
    selectedEvidenceId,
    isBusy,
    error,
    isEditMode,
    hasUnsavedDraft,
    boot,
    loadSample,
    uploadAndAnalyze,
    reanalyze,
    saveDraftAndReanalyze,
    undoDraft,
    discardDraft,
    setEditMode,
    exportResult,
    setActiveTab,
    setActivePage,
    focusEvidence,
    focusFromEvidence,
    saveRelation,
    removeRelation,
    regenerateAudit,
    updateClauseStructuredField,
  } = useContractStore();

  useEffect(() => {
    void boot();
  }, [boot, refreshToken]);

  useEffect(() => {
    if (!activeEntity) return;
    const element = document.getElementById(`card-${activeEntity.id}`);
    if (element) {
      window.setTimeout(() => {
        element.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 80);
    }
  }, [activeEntity, activeTab]);

  const visibleResult = draftResult ?? result;
  const contractNumber = useMemo(() => deriveContractNumber(visibleResult?.keyFacts ?? []), [visibleResult?.keyFacts]);
  const currentTask = task ?? visibleResult?.task ?? null;

  const openKnowledgeReview = () => {
    setActiveTab("knowledge");
    window.setTimeout(() => {
      const preferredTarget =
        currentTask?.knowledgeBaseReview?.status === "completed"
          ? document.getElementById("knowledge-base-review-result")
          : null;
      const fallbackTarget = document.getElementById("knowledge-base-review-panel");
      (preferredTarget ?? fallbackTarget)?.scrollIntoView({ behavior: "smooth", block: "start", inline: "nearest" });
    }, 120);
  };

  const leftPanel = !visibleResult ? (
    isBusy ? (
      <LoadingState
        label={task?.currentStage === "ocr_running" ? "正在识别文本..." : "正在处理合同..."}
        detail={task?.stageDetail ?? "请稍候"}
        progress={task?.progressPercent ?? 0}
      />
    ) : (
      <EmptyState
        title="上传合同"
        description="支持 PDF 与图片合同，系统将自动完成结构解析、证据定位与关注点生成。"
        actionLabel="上传合同"
        onAction={() => {
          const input = document.getElementById("contract-upload-input") as HTMLInputElement | null;
          input?.click();
        }}
      />
    )
  ) : (
    <ContractViewer
      pages={visibleResult.pages}
      activePage={activePage}
      selectedEvidenceId={selectedEvidenceId}
      onSelectPage={setActivePage}
      onEvidenceClick={(evidence) => focusFromEvidence(evidence)}
    />
  );

  const rightPanel = (
    <AnalysisTabs
      activeTab={activeTab}
      activeEntity={activeEntity}
      sections={visibleResult?.sections ?? []}
      clauses={visibleResult?.clauses ?? []}
      keyFacts={visibleResult?.keyFacts ?? []}
      contractNumber={contractNumber}
      task={currentTask}
      auditFocuses={auditFocuses}
      verificationItems={verificationItems}
      agentSteps={agentSteps}
      hasResult={Boolean(visibleResult)}
      isBusy={isBusy}
      isEditMode={isEditMode}
      hasUnsavedDraft={hasUnsavedDraft}
      onTabChange={setActiveTab}
      onSectionSelect={(section) =>
        section.evidenceId ? focusEvidence(section.evidenceId, "sections", { kind: "section", id: section.id }) : undefined
      }
      onClauseSelect={(clause) => focusEvidence(clause.evidenceId, "clauses", { kind: "clause", id: clause.id })}
      onAuditSelect={(focus) => {
        const relatedClause = visibleResult?.clauses.find((item) => item.id === focus.evidenceClauseIds[0]);
        if (relatedClause) {
          focusEvidence(relatedClause.evidenceId, "audit", { kind: "audit", id: focus.id });
        }
      }}
      onToggleEditMode={setEditMode}
      onStructuredFieldChange={updateClauseStructuredField}
      onUndoDraft={undoDraft}
      onDiscardDraft={discardDraft}
      onSaveDraft={() => void saveDraftAndReanalyze()}
    />
  );

  const completedSteps = agentSteps?.length ?? 0;
  const externalPendingCount = verificationItems?.filter((item) => item.needExternalTool).length ?? 0;

  const footer = visibleResult ? (
    <section className="glass-panel rounded-[24px] border border-white/8 px-5 py-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">任务编号</div>
          <div className="mt-2 text-sm text-white">{visibleResult.task.taskId}</div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Agent 状态</div>
          <div className="mt-2 text-sm text-white">已完成 {completedSteps} 个步骤</div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">待外部核验</div>
          <div className="mt-2 text-sm text-white">{externalPendingCount} 项</div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">模型服务</div>
          <div className="mt-2 text-sm text-white">{health?.text_model ?? visibleResult.task.modelName}</div>
        </div>
      </div>
    </section>
  ) : null;

  return (
    <>
      <AppShell
        header={
          <div className="space-y-3">
            <HeaderBar
              task={currentTask}
              health={health}
              busy={isBusy}
              contractNumber={contractNumber}
              onOpenAuditConfig={() => setAuditConfigOpen(true)}
              onOpenKnowledgeReview={openKnowledgeReview}
              onLoadSample={() => void loadSample()}
              onUpload={(file) => void uploadAndAnalyze(file)}
              onReanalyze={() => void reanalyze()}
              onExport={exportResult}
            />
            {error ? <ErrorBanner message={error} /> : null}
          </div>
        }
        left={leftPanel}
        right={rightPanel}
        footer={footer}
      />
      <AuditConfigModal open={auditConfigOpen} onClose={() => setAuditConfigOpen(false)}>
        <RelationConfigPanel
          relations={relations}
          activeId={activeEntity?.kind === "relation" ? activeEntity.id : null}
          onSave={(relation) => void saveRelation(relation)}
          onDelete={(relationId) => void removeRelation(relationId)}
          onRegenerateAudit={() => void regenerateAudit()}
          allowRegenerate={Boolean(visibleResult)}
        />
      </AuditConfigModal>
    </>
  );
}
