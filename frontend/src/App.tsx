import { useEffect, useMemo } from "react";
import { AnalysisTabs } from "./components/analysis/AnalysisTabs";
import { ContractViewer } from "./components/contract/ContractViewer";
import { AppShell } from "./components/layout/AppShell";
import { HeaderBar } from "./components/layout/HeaderBar";
import { ErrorBanner } from "./components/shared/ErrorBanner";
import { EmptyState } from "./components/shared/EmptyState";
import { LoadingState } from "./components/shared/LoadingState";
import type { KeyFact } from "./types/contract";
import { useContractStore } from "./store/contractStore";

function deriveContractNumber(keyFacts: KeyFact[]): string | null {
  const fact = keyFacts.find((item) => item.label === "合同编号" || item.label === "协议编号");
  const value = fact?.value.trim();
  if (!value || value === "未提取" || value === "待提取") {
    return null;
  }
  return value;
}

function App() {
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
      relations={relations}
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
      onRelationSave={(relation) => void saveRelation(relation)}
      onRelationDelete={(relationId) => void removeRelation(relationId)}
      onRegenerateAudit={() => void regenerateAudit()}
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
      {isBusy ? `处理中：${currentTask?.progressPercent ?? 0}% · ${currentTask?.stageDetail ?? "等待服务返回进度"}` : "工作台已就绪，可先配置审计策略再上传合同。"}
    </footer>
  );

  return (
    <AppShell
      header={
        <div className="space-y-3">
          <HeaderBar
            task={currentTask}
            busy={isBusy}
            contractNumber={contractNumber}
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
  );
}

export default App;
