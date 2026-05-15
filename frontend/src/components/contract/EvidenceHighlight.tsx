import { cn } from "../../lib/cn";
import type { EvidenceRef } from "../../types/contract";

export function EvidenceHighlight({
  evidence,
  scale,
  active,
  onClick,
}: {
  evidence: EvidenceRef;
  scale: number;
  active: boolean;
  onClick: () => void;
}) {
  const [x, y, width, height] = evidence.bbox;
  const accent =
    evidence.accent === "amber"
      ? "border-amber-400 bg-amber-400/14"
      : "border-cyan-400 bg-cyan-400/12";

  return (
    <button
      type="button"
      aria-label={evidence.text}
      onClick={onClick}
      className={cn(
        "absolute rounded-lg border text-left transition duration-200",
        accent,
        active
          ? "z-20 shadow-[0_0_0_2px_rgba(255,255,255,0.88),0_0_28px_rgba(67,214,255,0.18)]"
          : "z-10 opacity-0 pointer-events-none",
      )}
      style={{
        left: x * scale,
        top: y * scale,
        width: width * scale,
        height: height * scale,
      }}
    >
      {active ? (
        <span className="absolute -top-7 left-0 rounded-full border border-white/10 bg-slate-950/85 px-2.5 py-1 text-[10px] tracking-[0.18em] text-white uppercase">
          {evidence.segmentCount > 1 ? `证据片段 ${evidence.segmentIndex + 1}/${evidence.segmentCount}` : "证据定位"}
        </span>
      ) : null}
    </button>
  );
}
