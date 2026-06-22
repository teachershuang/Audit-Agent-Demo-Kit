import { FileText, ListTree, Radar, ShieldCheck, Workflow } from "lucide-react";
import type { AgentStep, AuditFocus, VerificationItem } from "../../types/audit";
import type { AnalysisTab, ClauseTag, ContractSection, ContractTask, KeyFact } from "../../types/contract";
import { AgentTimeline } from "./AgentTimeline";
import { AuditFocusList } from "./AuditFocusList";
import { ClauseTagList } from "./ClauseTagList";
import { KnowledgeBaseReviewPanel } from "./KnowledgeBaseReviewPanel";
import { SectionTree } from "./SectionTree";
import { VerificationPanel } from "./VerificationPanel";

interface AnalysisTabsProps {
  activeTab: AnalysisTab;
  activeEntity: { kind: string; id: string } | null;
  sections: ContractSection[];
  clauses: ClauseTag[];
  keyFacts: KeyFact[];
  contractNumber: string | null;
  task: ContractTask | null;
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
  hasResult: boolean;
  isBusy: boolean;
  isEditMode: boolean;
  hasUnsavedDraft: boolean;
  onTabChange: (tab: AnalysisTab) => void;
  onSectionSelect: (section: ContractSection) => void;
  onClauseSelect: (clause: ClauseTag) => void;
  onAuditSelect: (focus: AuditFocus) => void;
  onToggleEditMode: (enabled: boolean) => void;
  onStructuredFieldChange: (patch: { clauseId: string; fieldKey: string; value: unknown }) => void;
  onUndoDraft: () => void;
  onDiscardDraft: () => void;
  onSaveDraft: () => void;
}

const overviewSlots = [
  { title: "合同编号", labels: ["合同编号", "协议编号"] },
  { title: "主体摘要", labels: ["主体摘要", "合同基本信息"] },
  { title: "甲乙方信息", labels: ["甲乙方信息"] },
  { title: "服务内容", labels: ["服务内容"] },
] as const;

function EmptyTabPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[22px] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8">
      <div className="text-sm font-medium text-white">{title}</div>
      <div className="mt-2 text-sm leading-7 text-slate-400">{description}</div>
    </div>
  );
}

export function AnalysisTabs({
  activeTab,
  activeEntity,
  sections,
  clauses,
  keyFacts,
  contractNumber,
  task,
  auditFocuses,
  verificationItems,
  agentSteps,
  hasResult,
  isBusy,
  isEditMode,
  hasUnsavedDraft,
  onTabChange,
  onSectionSelect,
  onClauseSelect,
  onAuditSelect,
  onToggleEditMode,
  onStructuredFieldChange,
  onUndoDraft,
  onDiscardDraft,
  onSaveDraft,
}: AnalysisTabsProps) {
  const showVerificationTab = verificationItems.some((item) => item.needExternalTool || item.source !== "knowledge_base");
  const tabItems = [
    { id: "sections" as AnalysisTab, shortLabel: "章节还原", icon: ListTree },
    { id: "clauses" as AnalysisTab, shortLabel: "条款结构", icon: FileText },
    { id: "audit" as AnalysisTab, shortLabel: "审查关注点", icon: Radar },
    ...(showVerificationTab ? [{ id: "verification" as AnalysisTab, shortLabel: "校验证据", icon: ShieldCheck }] : []),
    { id: "knowledge" as AnalysisTab, shortLabel: "制度校验", icon: ShieldCheck },
    { id: "logs" as AnalysisTab, shortLabel: "Agent 过程", icon: Workflow },
  ];

  const overviewCards = overviewSlots.map((slot) => {
    const slotLabels = slot.labels as readonly string[];
    let fact = keyFacts.find((item) => slotLabels.includes(item.label)) ?? null;
    if (!fact && slot.title === "甲乙方信息") {
      const partyA = keyFacts.find((item) => item.label === "甲方");
      const partyB = keyFacts.find((item) => item.label === "乙方");
      if (partyA || partyB) {
        fact = {
          id: "overview_parties",
          label: "甲乙方信息",
          value: [partyA ? `甲方：${partyA.value}` : "", partyB ? `乙方：${partyB.value}` : ""].filter(Boolean).join("；"),
          page: partyA?.page ?? partyB?.page ?? 1,
          confidence: Math.max(partyA?.confidence ?? 0, partyB?.confidence ?? 0),
          evidenceId: partyA?.evidenceId ?? partyB?.evidenceId ?? null,
          notes: null,
        };
      }
    }
    return {
      title: slot.title,
      value: fact?.value?.trim() || "未提取",
      confidence: fact?.confidence ?? 0,
      muted: !fact || fact.value.trim() === "未提取",
    };
  });

  const renderActiveTab = () => {
    if (!hasResult) {
      if (activeTab === "sections") return <EmptyTabPanel title="等待合同上传" description="上传后显示章节结构。" />;
      if (activeTab === "clauses") return <EmptyTabPanel title="等待条款识别" description="上传后显示条款结构。" />;
      if (activeTab === "audit") return <EmptyTabPanel title="等待审查关注点生成" description="解析完成后显示审查关注点。" />;
      if (activeTab === "verification") return <EmptyTabPanel title="等待校验结果" description="解析完成后显示校验结果。" />;
      if (activeTab === "knowledge") return <EmptyTabPanel title="等待制度校验" description="上传后显示制度校验进度。" />;
      return <EmptyTabPanel title="等待 Agent 过程日志" description="上传后显示处理步骤。" />;
    }
    if (activeTab === "sections") {
      return <SectionTree sections={sections} activeId={activeEntity?.kind === "section" ? activeEntity.id : null} onSelect={onSectionSelect} />;
    }
    if (activeTab === "clauses") {
      return (
        <ClauseTagList
          clauses={clauses}
          activeId={activeEntity?.kind === "clause" ? activeEntity.id : null}
          editMode={isEditMode}
          hasUnsavedDraft={hasUnsavedDraft}
          onSelect={onClauseSelect}
          onToggleEditMode={onToggleEditMode}
          onUndoDraft={onUndoDraft}
          onDiscardDraft={onDiscardDraft}
          onSaveDraft={onSaveDraft}
          onStructuredFieldChange={onStructuredFieldChange}
        />
      );
    }
    if (activeTab === "audit") {
      return <AuditFocusList items={auditFocuses} activeId={activeEntity?.kind === "audit" ? activeEntity.id : null} onSelect={onAuditSelect} />;
    }
    if (activeTab === "verification" && showVerificationTab) {
      return <VerificationPanel items={verificationItems} clauses={clauses} />;
    }
    if (activeTab === "knowledge") {
      return <KnowledgeBaseReviewPanel task={task} auditFocuses={auditFocuses} verificationItems={verificationItems} />;
    }
    return <AgentTimeline steps={agentSteps} />;
  };

  return (
    <div className="glass-panel flex h-full min-h-0 flex-col rounded-[28px] border border-white/8 p-4">
      <div className="border-b border-white/8 pb-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-200/70">Review Intelligence Dashboard</p>
        <h2 className="mt-1 font-display text-xl text-white">智能解析结果</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(0,1fr))]">
          {overviewCards.map((card, index) => (
            <div
              key={card.title}
              className={`rounded-2xl border px-4 py-3 ${
                index === 0 ? "border-cyan-400/14 bg-cyan-400/[0.06]" : "border-white/8 bg-white/[0.03]"
              }`}
            >
              <div className="text-[11px] uppercase tracking-[0.22em] text-slate-400">{card.title}</div>
              <div className={`mt-2 line-clamp-3 text-sm ${card.muted ? "text-slate-400" : "text-white"}`}>
                {card.title === "合同编号" ? contractNumber ?? "未提取" : card.value}
              </div>
              {!card.muted ? <div className="mt-2 text-[11px] text-cyan-100/75">置信度 {Math.round(card.confidence * 100)}%</div> : null}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-5">
          {tabItems.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onTabChange(tab.id)}
                className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-full border px-3 py-2 text-sm font-medium transition ${
                  active
                    ? "border-cyan-300/45 bg-cyan-400/12 text-cyan-50 shadow-[0_10px_30px_rgba(34,211,238,0.12)]"
                    : "border-white/10 bg-white/[0.04] text-slate-300 hover:border-cyan-400/20 hover:bg-white/[0.06]"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="truncate">{tab.shortLabel}</span>
              </button>
            );
          })}
        </div>
      </div>

      {isBusy && !hasResult ? (
        <div className="mt-4 rounded-2xl border border-cyan-400/16 bg-cyan-400/[0.06] px-4 py-3 text-sm text-cyan-50/90">解析中，完成后自动刷新。</div>
      ) : null}

      <div className="thin-scrollbar mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">{renderActiveTab()}</div>
    </div>
  );
}
