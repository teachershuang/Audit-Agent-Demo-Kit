import type { RiskLevel } from "../../types/audit";
import { cn } from "../../lib/cn";

const riskMap: Record<RiskLevel, string> = {
  low: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
  medium: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  high: "border-rose-400/30 bg-rose-400/10 text-rose-100",
  pending_verification: "border-cyan-400/30 bg-cyan-400/10 text-cyan-100",
};

const labelMap: Record<RiskLevel, string> = {
  low: "低",
  medium: "中",
  high: "高",
  pending_verification: "待核验",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full border px-3 py-1 text-[11px] font-semibold tracking-[0.18em] uppercase",
        riskMap[level],
      )}
    >
      风险 {labelMap[level]}
    </span>
  );
}
