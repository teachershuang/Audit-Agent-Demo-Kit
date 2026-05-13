import type { AuditFocus } from "../../types/audit";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";
import { RiskBadge } from "../shared/RiskBadge";

export function AuditFocusCard({
  focus,
  active,
  onSelect,
}: {
  focus: AuditFocus;
  active: boolean;
  onSelect: (focus: AuditFocus) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(focus)}
      id={`card-${focus.id}`}
      className={`w-full rounded-[24px] border p-4 text-left transition ${
        active ? "border-cyan-300/40 bg-cyan-400/[0.08]" : "border-white/8 bg-white/[0.03]"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">审计关注方向</p>
          <h3 className="mt-1 text-base font-semibold text-white">{focus.title}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <RiskBadge level={focus.riskLevel} />
          <ConfidenceBadge value={focus.confidence} />
        </div>
      </div>
      <p className="mt-3 text-sm leading-7 text-slate-300">{focus.reason}</p>
      <div className="mt-4 grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300 md:grid-cols-2">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">证据位置</div>
          <div className="mt-2">{focus.locationText}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">当前判断依据</div>
          <div className="mt-2">{focus.currentBasis}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">依赖数据</div>
          <div className="mt-2">{focus.dependsOn.join(" / ")}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">建议后续工具</div>
          <div className="mt-2">{focus.futureTools.join(" / ")}</div>
        </div>
      </div>
      <p className="mt-4 text-sm leading-7 text-cyan-100/90">{focus.humanReviewSuggestion}</p>
    </button>
  );
}
