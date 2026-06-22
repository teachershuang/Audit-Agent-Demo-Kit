import { useEffect, useRef } from "react";
import { getApiBaseUrlSync } from "../../services/api";
import { cn } from "../../lib/cn";
import type { ContractPage } from "../../types/contract";

function resolveImageUrl(path: string | null | undefined) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${getApiBaseUrlSync()}${path}`;
}

export function PageThumbnailList({
  pages,
  activePage,
  onSelect,
}: {
  pages: ContractPage[];
  activePage: number;
  onSelect: (page: number) => void;
}) {
  const activeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activePage]);

  return (
    <div className="thin-scrollbar flex h-full gap-3 overflow-x-auto pb-2 xl:flex-col xl:overflow-y-auto xl:pr-1">
      {pages.map((page) => {
        const imageUrl = resolveImageUrl(page.imageUrl);
        const active = activePage === page.page;
        return (
          <button
            key={page.page}
            ref={active ? activeRef : undefined}
            type="button"
            onClick={() => onSelect(page.page)}
            className={cn(
              "min-w-[168px] rounded-[20px] border p-3 text-left transition xl:min-w-0",
              active ? "border-cyan-300/40 bg-cyan-400/10" : "border-white/8 bg-white/[0.03] hover:border-cyan-400/24",
            )}
          >
            <div className="overflow-hidden rounded-[16px] border border-white/8 bg-slate-100/95">
              {imageUrl ? (
                <img src={imageUrl} alt={`第 ${page.page} 页`} className="h-[176px] w-full object-cover object-top" />
              ) : (
                <div className="flex h-[176px] items-center justify-center px-4 text-sm text-slate-500">暂无页预览</div>
              )}
            </div>
            <div className="mt-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-400">Page {page.page}</div>
              <div className="mt-2 text-sm font-semibold text-white">第 {page.page} 页</div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
