import { FileText, ListTree, Radar, ShieldCheck, Workflow } from "lucide-react";
import type { AgentStep, AuditFocus, VerificationItem } from "../../types/audit";
import type { AnalysisTab, ClauseTag, ContractSection, KeyFact } from "../../types/contract";
import { AgentTimeline } from "./AgentTimeline";
import { AuditFocusList } from "./AuditFocusList";
import { ClauseTagList } from "./ClauseTagList";
import { SectionTree } from "./SectionTree";
import { VerificationPanel } from "./VerificationPanel";

const tabItems: Array<{
  id: AnalysisTab;
  shortLabel: string;
  icon: typeof ListTree;
}> = [
  { id: "sections", shortLabel: "章节还原", icon: ListTree },
  { id: "clauses", shortLabel: "条款标签", icon: FileText },
  { id: "audit", shortLabel: "审计关注点", icon: Radar },
  { id: "verification", shortLabel: "校验证据链", icon: ShieldCheck },
  { id: "logs", shortLabel: "Agent 过程", icon: Workflow },
];

interface AnalysisTabsProps {
  activeTab: AnalysisTab;
  activeEntity: { kind: string; id: string } | null;
  sections: ContractSection[];
  clauses: ClauseTag[];
  keyFacts: KeyFact[];
  contractNumber: string | null;
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
  agentSteps: AgentStep[];
  hasResult: boolean;
  isBusy: boolean;
  onTabChange: (tab: AnalysisTab) => void;
  onSectionSelect: (section: ContractSection) => void;
  onClauseSelect: (clause: ClauseTag) => void;
  onAuditSelect: (focus: AuditFocus) => void;
}

const overviewSlots = [
  { title: "合同编号", labels: ["合同编号", "协议编号"] },
  { title: "主体摘要", labels: ["主体摘要", "合同基本信息"] },
  { title: "甲乙方信息", labels: ["甲乙方信息"] },
  { title: "服务内容", labels: ["服务内容"] },
] as const;

function EmptyTabPanel({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
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
  auditFocuses,
  verificationItems,
  agentSteps,
  hasResult,
  isBusy,
  onTabChange,
  onSectionSelect,
  onClauseSelect,
  onAuditSelect,
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

  const renderActiveTab = () => {
    if (!hasResult) {
      if (activeTab === "sections") {
        return (
          <EmptyTabPanel
            title="等待合同上传"
            description="上传合同后，这里会按合同原始顺序展示章节结构，并保留条、款、附件等层级信息。"
          />
        );
      }
      if (activeTab === "clauses") {
        return (
          <EmptyTabPanel
            title="等待条款识别"
            description="上传合同后，这里会展示结构化条款标签、交叉引用关系，以及可供规则引擎使用的字段。"
          />
        );
      }
      if (activeTab === "audit") {
        return (
          <EmptyTabPanel
            title="等待审计关注点生成"
            description="完成解析后，这里会同时展示用户配置触发和 Agent 主动发现的关注方向。"
          />
        );
      }
      if (activeTab === "verification") {
        return (
          <EmptyTabPanel
            title="等待校验结果"
            description="合同解析完成后，这里会展示规则命中、模型校验和证据链说明。"
          />
        );
      }
      return (
        <EmptyTabPanel
          title="等待 Agent 过程日志"
          description="上传合同后，这里会显示每一步解析动作、所用工具和输出摘要。"
        />
      );
    }

    if (activeTab === "sections") {
      return (
        <SectionTree
          sections={sections}
          activeId={activeEntity?.kind === "section" ? activeEntity.id : null}
          onSelect={onSectionSelect}
        />
      );
    }
    if (activeTab === "clauses") {
      return (
        <ClauseTagList
          clauses={clauses}
          activeId={activeEntity?.kind === "clause" ? activeEntity.id : null}
          onSelect={onClauseSelect}
        />
      );
    }
    if (activeTab === "audit") {
      return (
        <AuditFocusList
          items={auditFocuses}
          activeId={activeEntity?.kind === "audit" ? activeEntity.id : null}
          onSelect={onAuditSelect}
        />
      );
    }
    if (activeTab === "verification") {
      return <VerificationPanel items={verificationItems} clauses={clauses} />;
    }
    return <AgentTimeline steps={agentSteps} />;
  };

  return (
    <div className="glass-panel flex h-full min-h-[720px] flex-col rounded-[28px] border border-white/8 p-4">
      <div className="border-b border-white/8 pb-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-200/70">
          Audit Intelligence Dashboard
        </p>
        <h2 className="mt-1 font-display text-xl text-white">智能解析结果</h2>
        <p className="mt-2 text-sm text-slate-300">
          章节区和条款区职责分开：章节负责顺序还原，条款负责结构化理解、引用关系与规则输入准备。
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
        <div className="mt-4 rounded-2xl border border-cyan-400/16 bg-cyan-400/[0.06] px-4 py-3 text-sm text-cyan-50/90">
          合同正在解析中。审计配置请通过右上角入口维护；建议在当前任务完成后再调整配置并重新生成关注点。
        </div>
      ) : null}

      <div className="thin-scrollbar mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">{renderActiveTab()}</div>
    </div>
  );
}
