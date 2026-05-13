import { cn } from "../../lib/cn";

interface ConfidenceBadgeProps {
  value: number;
  label?: string;
}

export function ConfidenceBadge({ value, label = "置信度" }: ConfidenceBadgeProps) {
  const percent = Math.round(value * 100);
  const tone =
    value >= 0.85
      ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-200"
      : value >= 0.65
        ? "border-amber-400/35 bg-amber-400/10 text-amber-100"
        : "border-rose-400/35 bg-rose-400/10 text-rose-100";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium tracking-[0.18em] uppercase",
        tone,
      )}
    >
      <span>{label}</span>
      <span>{percent}%</span>
    </span>
  );
}
