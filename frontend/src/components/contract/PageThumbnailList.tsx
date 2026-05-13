import { cn } from "../../lib/cn";
import type { ContractPage } from "../../types/contract";

export function PageThumbnailList({
  pages,
  activePage,
  onSelect,
}: {
  pages: ContractPage[];
  activePage: number;
  onSelect: (page: number) => void;
}) {
  return (
    <div className="thin-scrollbar flex max-h-[calc(100vh-21rem)] gap-3 overflow-x-auto pb-2 xl:max-h-none xl:flex-col xl:overflow-y-auto xl:pr-1">
      {pages.map((page) => (
        <button
          key={page.page}
          type="button"
          onClick={() => onSelect(page.page)}
          className={cn(
            "min-w-[148px] rounded-2xl border px-3 py-3 text-left transition xl:min-w-0",
            activePage === page.page
              ? "border-cyan-300/40 bg-cyan-400/10"
              : "border-white/8 bg-white/[0.03] hover:border-cyan-400/24",
          )}
        >
          <div className="rounded-xl border border-white/8 bg-slate-100/95 px-3 py-5 text-slate-700">
            <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-400">
              Page {page.page}
            </div>
            <div className="mt-2 line-clamp-2 text-sm font-semibold">{page.title}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
