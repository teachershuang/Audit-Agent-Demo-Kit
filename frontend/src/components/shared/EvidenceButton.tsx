import { ScanSearch } from "lucide-react";

export function EvidenceButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-100 transition hover:border-cyan-300 hover:bg-cyan-400/18"
    >
      <ScanSearch className="h-3.5 w-3.5" />
      定位原文
    </button>
  );
}
