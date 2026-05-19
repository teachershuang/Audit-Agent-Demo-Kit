import type { ClauseTag } from "../../types/contract";
import { EvidenceButton } from "../shared/EvidenceButton";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";

export function ClauseCard({
  clause,
  active,
  onSelect,
}: {
  clause: ClauseTag;
  active: boolean;
  onSelect: (clause: ClauseTag) => void;
}) {
  return (
    <article
      id={`card-${clause.id}`}
      className={`rounded-[22px] border p-4 transition ${
        active ? "border-cyan-300/40 bg-cyan-400/[0.08]" : "border-white/8 bg-white/[0.03]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">{clause.label}</p>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
              {clause.labelSource === "agent_discovered"
                ? "Agent 新发现"
                : clause.labelSource === "user_configured"
                  ? "用户配置"
                  : "核心标签"}
            </span>
          </div>
          <h3 className="mt-1 text-base font-semibold text-white">{clause.title}</h3>
          {clause.sectionTitle ? <p className="mt-1 text-xs text-slate-400">所属章节：{clause.sectionTitle}</p> : null}
        </div>
        <ConfidenceBadge value={clause.confidence} />
      </div>

      <p className="mt-3 text-sm leading-7 text-slate-300">{clause.summary}</p>

      {clause.references && clause.references.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {clause.references.map((reference) => (
            <span key={reference} className="rounded-full border border-cyan-400/16 bg-cyan-400/6 px-3 py-1 text-xs text-cyan-100">
              引用 {reference}
            </span>
          ))}
        </div>
      ) : null}

      {clause.structuredFields && Object.keys(clause.structuredFields).length > 0 ? (
        <div className="mt-3 rounded-2xl border border-cyan-400/16 bg-cyan-400/6 px-4 py-3 text-sm text-cyan-50/90">
          <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-200/60">结构化字段</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(clause.structuredFields).map(([key, value]) => (
              <span key={key} className="rounded-full border border-white/10 bg-slate-950/25 px-3 py-1 text-xs text-slate-200">
                {key}：{value}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {clause.discoveryReason ? (
        <div className="mt-3 rounded-2xl border border-cyan-400/16 bg-cyan-400/6 px-4 py-3 text-sm leading-7 text-cyan-50/90">
          {clause.discoveryReason}
        </div>
      ) : null}

      <blockquote className="mt-3 rounded-2xl border border-white/8 bg-slate-950/30 px-4 py-3 text-sm leading-7 text-slate-300">
        {clause.rawText}
      </blockquote>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span>页码 {clause.page}</span>
        <span>·</span>
        <span>{clause.needHumanReview ? "建议人工复核" : "自动识别较稳定"}</span>
        <span>·</span>
        <span>关联关注点 {clause.relatedAuditFocusIds.length}</span>
      </div>

      <div className="mt-4">
        <EvidenceButton onClick={() => onSelect(clause)} />
      </div>
    </article>
  );
}
