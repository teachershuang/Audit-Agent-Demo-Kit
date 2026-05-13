import { useEffect } from "react";
import { AppShell } from "./components/layout/AppShell";
import { HeaderBar } from "./components/layout/HeaderBar";
import { AnalysisTabs } from "./components/analysis/AnalysisTabs";
import { ContractViewer } from "./components/contract/ContractViewer";
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
      <LoadingState label="正在启动 Agent 解析链路..." />
    ) : (
      <EmptyState
        title="上传合同或直接加载示例"
        description="第一版 demo 支持使用 mock 合同直接演示完整流程，也支持上传 PDF / 图片触发后端 Agent 解析接口。"
        actionLabel="加载示例合同"
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
        title="解析结果区待激活"
        description="Agent 完成章节识别、条款标签、关注方向和证据链构建后，右侧将展示完整工作台视图。"
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
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">Agent 执行状态</div>
          <div className="mt-2 text-sm text-white">
            {agentSteps.length} 个步骤已装载，{verificationItems.filter((item) => item.needExternalTool).length} 项待外部数据核验
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">模型调用说明</div>
          <div className="mt-2 text-sm text-white">Qwen / Mock Hybrid，输出均要求可回溯至原文证据。</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">当前限制</div>
          <div className="mt-2 text-sm text-white">
            未接入规则引擎、知识图谱、企业工商库，相关结论均仅作关注方向。
          </div>
        </div>
      </div>
    </footer>
  ) : (
    <footer className="rounded-[24px] border border-dashed border-white/8 px-5 py-4 text-sm text-slate-400">
      Agent cockpit 已就绪，等待上传合同或加载示例。
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
