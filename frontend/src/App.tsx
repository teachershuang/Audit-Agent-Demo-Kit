import { useEffect, useMemo, useState } from "react";
import { AnalysisTabs } from "./components/analysis/AnalysisTabs";
import { ContractViewer } from "./components/contract/ContractViewer";
import { RelationConfigPanel } from "./components/config/RelationConfigPanel";
import { AppShell } from "./components/layout/AppShell";
import { HeaderBar } from "./components/layout/HeaderBar";
import { EmptyState } from "./components/shared/EmptyState";
import { ErrorBanner } from "./components/shared/ErrorBanner";
import { LoadingState } from "./components/shared/LoadingState";
import { useContractStore } from "./store/contractStore";
import type { KeyFact } from "./types/contract";

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
            <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">Audit Config Workspace</div>
            <h2 className="mt-1 text-xl font-semibold text-white">审计配置</h2>
            <p className="mt-1 text-sm text-slate-300">
              在上传合同之前独立维护关系关注、规则校验与外部核验策略。
            </p>
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

function App() {
  const [auditConfigOpen, setAuditConfigOpen] = useState(false);
  const {
    task,
    result,
    relations,
    auditFocuses,
    verificationItems,
    agentSteps,
    activeTab,
    activePage,
    activeEntity,
    selectedEvidenceId,
    isBusy,
    error,
    boot,
    loadSample,
    uploadAndAnalyze,
    reanalyze,
    exportResult,
    setActiveTab,
    focusEvidence,
    focusFromEvidence,
    saveRelation,
    removeRelation,
    regenerateAudit,
  } = useContractStore();

  useEffect(() => {
    void boot();
  }, [boot]);

  useEffect(() => {
    if (!activeEntity) return;
    const element = document.getElementById(`card-${activeEntity.id}`);
    if (element) {
      window.setTimeout(() => {
        element.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 80);
    }
  }, [activeEntity, activeTab]);

  const contractNumber = useMemo(() => deriveContractNumber(result?.keyFacts ?? []), [result?.keyFacts]);

  const leftPanel = !result ? (
    isBusy ? (
      <LoadingState
        label={task?.currentStage === "ocr_running" ? "正在识别扫描页面文本..." : "正在启动分析任务..."}
        detail={task?.stageDetail ?? "正在准备文档并调度解析链路。"}
        progress={task?.progressPercent ?? 0}
      />
    ) : (
      <EmptyState
        title="上传合同开始分析"
        description="支持 PDF 与图片合同。系统会完成结构还原、条款识别、证据定位与审计关注生成。"
        actionLabel="上传合同"
        onAction={() => {
          const input = document.getElementById("contract-upload-input") as HTMLInputElement | null;
          input?.click();
        }}
      />
    )
  ) : (
    <ContractViewer
      pages={result.pages}
      activePage={activePage}
      selectedEvidenceId={selectedEvidenceId}
      onSelectPage={(page) => useContractStore.setState({ activePage: page })}
      onEvidenceClick={(evidence) => focusFromEvidence(evidence)}
    />
  );

  const rightPanel = (
    <AnalysisTabs
      activeTab={activeTab}
      activeEntity={activeEntity}
      sections={result?.sections ?? []}
      clauses={result?.clauses ?? []}
      keyFacts={result?.keyFacts ?? []}
      contractNumber={contractNumber}
      auditFocuses={auditFocuses}
      verificationItems={verificationItems}
      agentSteps={agentSteps}
      hasResult={Boolean(result)}
      isBusy={isBusy}
      onTabChange={setActiveTab}
      onSectionSelect={(section) =>
        section.evidenceId ? focusEvidence(section.evidenceId, "sections", { kind: "section", id: section.id }) : undefined
      }
      onClauseSelect={(clause) => focusEvidence(clause.evidenceId, "clauses", { kind: "clause", id: clause.id })}
      onAuditSelect={(focus) => {
        const relatedClause = result?.clauses.find((item) => item.id === focus.evidenceClauseIds[0]);
        if (relatedClause) {
          focusEvidence(relatedClause.evidenceId, "audit", { kind: "audit", id: focus.id });
        }
      }}
    />
  );

  const completedSteps = agentSteps?.length ?? 0;
  const externalPendingCount = verificationItems?.filter((item) => item.needExternalTool).length ?? 0;
  const currentTask = task ?? result?.task ?? null;

  const footer = result ? (
    <footer className="glass-panel rounded-[24px] border border-white/8 px-5 py-4">
      <div className="grid gap-3 md:grid-cols-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">任务编号</div>
          <div className="mt-2 text-sm text-white">{result.task.taskId}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Agent 状态</div>
          <div className="mt-2 text-sm text-white">
            已完成 {completedSteps} 个步骤，仍有 {externalPendingCount} 项待外部核验
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">模型服务</div>
          <div className="mt-2 text-sm text-white">{result.task.modelName}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">证据链</div>
          <div className="mt-2 text-sm text-white">结果与原文位置保持联动映射</div>
        </div>
      </div>
    </footer>
  ) : (
    <footer className="rounded-[24px] border border-dashed border-white/8 px-5 py-4 text-sm text-slate-400">
      {isBusy
        ? `处理中：${currentTask?.progressPercent ?? 0}% · ${currentTask?.stageDetail ?? "等待服务返回进度"}`
        : "工作台已就绪，可先配置审计策略再上传合同。"}
    </footer>
  );

  return (
    <>
      <AppShell
        header={
          <div className="space-y-3">
            <HeaderBar
              task={currentTask}
              busy={isBusy}
              contractNumber={contractNumber}
              onOpenAuditConfig={() => setAuditConfigOpen(true)}
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
          allowRegenerate={Boolean(result)}
        />
      </AuditConfigModal>
    </>
  );
}

export default App;
