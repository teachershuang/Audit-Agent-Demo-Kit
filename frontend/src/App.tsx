import { useEffect } from "react";
import { AnalysisTabs } from "./components/analysis/AnalysisTabs";
import { ContractViewer } from "./components/contract/ContractViewer";
import { AppShell } from "./components/layout/AppShell";
import { HeaderBar } from "./components/layout/HeaderBar";
import { EmptyState } from "./components/shared/EmptyState";
import { LoadingState } from "./components/shared/LoadingState";
import { useContractStore } from "./store/contractStore";

function App() {
  const {
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

  const leftPanel = !result ? (
    isBusy ? (
      <LoadingState label="正在启动解析任务..." />
    ) : (
      <EmptyState
        title="上传合同开始分析"
        description="支持 PDF 与图片合同，上传后进入结构解析、条款识别与证据定位。"
        actionLabel="快速载入"
        onAction={() => void loadSample()}
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

  const rightPanel = !result ? (
    isBusy ? (
      <LoadingState label="等待解析结果..." />
    ) : (
      <EmptyState
        title="结果区待加载"
        description="完成解析后将在此显示章节、条款、关系配置、关注事项与证据链。"
      />
    )
  ) : (
    <AnalysisTabs
      activeTab={activeTab}
      activeEntity={activeEntity}
      sections={result.sections}
      clauses={result.clauses}
      relations={relations}
      auditFocuses={auditFocuses}
      verificationItems={verificationItems}
      agentSteps={agentSteps}
      onTabChange={setActiveTab}
      onSectionSelect={(section) =>
        section.evidenceId
          ? focusEvidence(section.evidenceId, "sections", { kind: "section", id: section.id })
          : undefined
      }
      onClauseSelect={(clause) =>
        focusEvidence(clause.evidenceId, "clauses", { kind: "clause", id: clause.id })
      }
      onAuditSelect={(focus) => {
        const relatedClause = result.clauses.find((item) => item.id === focus.evidenceClauseIds[0]);
        if (relatedClause) {
          focusEvidence(relatedClause.evidenceId, "audit", { kind: "audit", id: focus.id });
        }
      }}
      onRelationSave={(relation) => void saveRelation(relation)}
      onRelationDelete={(relationId) => void removeRelation(relationId)}
      onRegenerateAudit={() => void regenerateAudit()}
    />
  );

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
            {agentSteps.length} 个步骤已完成，{verificationItems.filter((item) => item.needExternalTool).length} 项待进一步校验
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">模型服务</div>
          <div className="mt-2 text-sm text-white">{result.task.modelName}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">证据链</div>
          <div className="mt-2 text-sm text-white">结果与原文位置同步映射</div>
        </div>
      </div>
    </footer>
  ) : (
    <footer className="rounded-[24px] border border-dashed border-white/8 px-5 py-4 text-sm text-slate-400">
      工作台已就绪
    </footer>
  );

  return (
    <AppShell
      header={
        <HeaderBar
          task={result?.task ?? null}
          busy={isBusy}
          onLoadSample={() => void loadSample()}
          onUpload={(file) => void uploadAndAnalyze(file)}
          onReanalyze={() => void reanalyze()}
          onExport={exportResult}
        />
      }
      left={leftPanel}
      right={rightPanel}
      footer={footer}
    />
  );
}

export default App;
