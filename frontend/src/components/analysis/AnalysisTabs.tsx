import { FileText, GitBranch, ListTree, Radar, ShieldCheck, Workflow } from "lucide-react";
import type { AgentStep, AuditFocus, VerificationItem } from "../../types/audit";
import type { AnalysisTab, ClauseTag, ContractSection, KeyFact } from "../../types/contract";
import type { RelationConfig } from "../../types/relation";
import { AgentTimeline } from "./AgentTimeline";
import { AuditFocusList } from "./AuditFocusList";
import { ClauseTagList } from "./ClauseTagList";
import { SectionTree } from "./SectionTree";
import { VerificationPanel } from "./VerificationPanel";
import { RelationConfigPanel } from "../config/RelationConfigPanel";

const tabItems: Array<{
  id: AnalysisTab;
  label: string;
  shortLabel: string;
  icon: typeof ListTree;
}> = [
  { id: "sections", label: "章节还原", shortLabel: "章节还原", icon: ListTree },
  { id: "clauses", label: "条款标签", shortLabel: "条款标签", icon: FileText },
  { id: "relations", label: "关系配置", shortLabel: "关系配置", icon: GitBranch },
  { id: "audit", label: "审计关注点", shortLabel: "审计关注点", icon: Radar },
  { id: "verification", label: "校验证据链", shortLabel: "校验证据链", icon: ShieldCheck },
  { id: "logs", label: "Agent 过程日志", shortLabel: "Agent 过程", icon: Workflow },
];

interface AnalysisTabsProps {
  activeTab: AnalysisTab;
  activeEntity: { kind: string; id: string } | null;
  sections: ContractSection[];
  clauses: ClauseTag[];
  keyFacts: KeyFact[];
  contractNumber: string | null;
  relations: RelationConfig[];
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
  onTabChange: (tab: AnalysisTab) => void;
  onSectionSelect: (section: ContractSection) => void;
  onClauseSelect: (clause: ClauseTag) => void;
  onAuditSelect: (focus: AuditFocus) => void;
  onRelationSave: (relation: RelationConfig) => void;
  onRelationDelete: (relationId: string) => void;
  onRegenerateAudit: () => void;
}

const overviewSlots = [
  { title: "合同编号", labels: ["合同编号", "协议编号"] },
  { title: "主体摘要", labels: ["主体摘要", "合同基本信息"] },
  { title: "甲乙方信息", labels: ["甲乙方信息"] },
  { title: "服务内容", labels: ["服务内容"] },
] as const;

export function AnalysisTabs({
  activeTab,
  activeEntity,
  sections,
  clauses,
  keyFacts,
  contractNumber,
  relations,
  auditFocuses,
  verificationItems,
  agentSteps,
  onTabChange,
  onSectionSelect,
  onClauseSelect,
  onAuditSelect,
  onRelationSave,
  onRelationDelete,
  onRegenerateAudit,
}: AnalysisTabsProps) {
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
          value: [partyA ? `甲方：${partyA.value}` : "", partyB ? `乙方：${partyB.value}` : ""]
            .filter(Boolean)
            .join("；"),
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

  return (
    <div className="glass-panel flex h-full min-h-[720px] flex-col rounded-[28px] border border-white/8 p-4">
      <div className="border-b border-white/8 pb-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-200/70">
          Audit Intelligence Dashboard
        </p>
        <h2 className="mt-1 font-display text-xl text-white">智能解析结果</h2>
        <p className="mt-2 text-sm text-slate-300">
          按章节、条款、关系配置、关注事项、校验与过程分区查看，右侧分析不会再拖动左侧原件区。
        </p>
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
              {!card.muted ? (
                <div className="mt-2 text-[11px] text-cyan-100/75">置信度 {Math.round(card.confidence * 100)}%</div>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-6">
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

      <div className="thin-scrollbar mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        {activeTab === "sections" ? (
          <SectionTree
            sections={sections}
            activeId={activeEntity?.kind === "section" ? activeEntity.id : null}
            onSelect={onSectionSelect}
          />
        ) : null}
        {activeTab === "clauses" ? (
          <ClauseTagList
            clauses={clauses}
            activeId={activeEntity?.kind === "clause" ? activeEntity.id : null}
            onSelect={onClauseSelect}
          />
        ) : null}
        {activeTab === "relations" ? (
          <RelationConfigPanel
            relations={relations}
            activeId={activeEntity?.kind === "relation" ? activeEntity.id : null}
            onSave={onRelationSave}
            onDelete={onRelationDelete}
            onRegenerateAudit={onRegenerateAudit}
          />
        ) : null}
        {activeTab === "audit" ? (
          <AuditFocusList
            items={auditFocuses}
            activeId={activeEntity?.kind === "audit" ? activeEntity.id : null}
            onSelect={onAuditSelect}
          />
        ) : null}
        {activeTab === "verification" ? (
          <VerificationPanel items={verificationItems} clauses={clauses} />
        ) : null}
        {activeTab === "logs" ? <AgentTimeline steps={agentSteps} /> : null}
      </div>
    </div>
  );
}
