import type { ContractSection } from "../../types/contract";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";

export function SectionTree({
  sections,
  activeId,
  onSelect,
}: {
  sections: ContractSection[];
  activeId: string | null;
  onSelect: (section: ContractSection) => void;
}) {
  return (
    <div className="space-y-3">
      {sections.map((section) => (
        <button
          key={section.id}
          type="button"
          onClick={() => onSelect(section)}
          id={`card-${section.id}`}
          className={`w-full rounded-[22px] border p-4 text-left transition ${
            activeId === section.id
              ? "border-cyan-300/40 bg-cyan-400/[0.08]"
              : "border-white/8 bg-white/[0.03] hover:border-cyan-400/22"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">
                L{section.level} · Page {section.page}
              </p>
              <h3 className="mt-1 text-base font-semibold text-white">{section.title}</h3>
            </div>
            <ConfidenceBadge value={section.confidence} />
          </div>
          <p className="mt-3 text-sm leading-7 text-slate-300">{section.summary}</p>
          <div className="mt-4 text-xs text-slate-400">
            {section.evidenceId ? "已建立证据定位" : "缺少证据定位"}
          </div>
        </button>
      ))}
    </div>
  );
}
