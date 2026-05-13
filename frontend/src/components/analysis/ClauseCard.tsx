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
          <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">{clause.label}</p>
          <h3 className="mt-1 text-base font-semibold text-white">{clause.title}</h3>
        </div>
        <ConfidenceBadge value={clause.confidence} />
      </div>

      <p className="mt-3 text-sm leading-7 text-slate-300">{clause.summary}</p>
      <blockquote className="mt-3 rounded-2xl border border-white/8 bg-slate-950/30 px-4 py-3 text-sm leading-7 text-slate-300">
        {clause.rawText}
      </blockquote>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span>页码 {clause.page}</span>
        <span>·</span>
        <span>{clause.needHumanReview ? "建议人工复核" : "自动识别稳定"}</span>
        <span>·</span>
        <span>关联关注点 {clause.relatedAuditFocusIds.length}</span>
      </div>

      <div className="mt-4">
        <EvidenceButton onClick={() => onSelect(clause)} />
      </div>
    </article>
  );
}
