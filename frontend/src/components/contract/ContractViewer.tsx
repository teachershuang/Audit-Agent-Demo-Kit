import { Minus, Plus, SearchCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getApiBaseUrlSync } from "../../services/api";
import type { ContractPage, EvidenceRef } from "../../types/contract";
import { EvidenceHighlight } from "./EvidenceHighlight";
import { PageThumbnailList } from "./PageThumbnailList";

interface ContractViewerProps {
  pages: ContractPage[];
  activePage: number;
  selectedEvidenceId: string | null;
  onSelectPage: (page: number) => void;
  onEvidenceClick: (evidence: EvidenceRef) => void;
}

function resolveImageUrl(path: string | null | undefined) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${getApiBaseUrlSync()}${path}`;
}

export function ContractViewer({
  pages,
  activePage,
  selectedEvidenceId,
  onSelectPage,
  onEvidenceClick,
}: ContractViewerProps) {
  const [zoom, setZoom] = useState(0.98);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Record<number, HTMLElement | null>>({});
  const currentVisiblePageRef = useRef<number>(activePage);
  const allEvidences = useMemo(() => pages.flatMap((page) => page.evidences), [pages]);
  const activeEvidence = useMemo(
    () =>
      allEvidences.find((evidence) => evidence.id === selectedEvidenceId && evidence.isPrimary) ??
      allEvidences.find((evidence) => evidence.id === selectedEvidenceId) ??
      null,
    [allEvidences, selectedEvidenceId],
  );

  useEffect(() => {
    if (!containerRef.current || pages.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visibleEntries = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio);
        const topEntry = visibleEntries[0];
        if (!topEntry) return;
        const page = Number(topEntry.target.getAttribute("data-page"));
        if (!Number.isFinite(page) || currentVisiblePageRef.current === page) return;
        currentVisiblePageRef.current = page;
        onSelectPage(page);
      },
      {
        root: containerRef.current,
        threshold: [0.35, 0.6, 0.85],
      },
    );
    pages.forEach((page) => {
      const node = pageRefs.current[page.page];
      if (node) observer.observe(node);
    });
    return () => observer.disconnect();
  }, [pages, onSelectPage]);

  useEffect(() => {
    if (!activeEvidence) return;
    const target = pageRefs.current[activeEvidence.page];
    if (target) {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [activeEvidence]);

  const handleSelectPage = (page: number) => {
    onSelectPage(page);
    pageRefs.current[page]?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  return (
    <div className="glass-panel flex h-full min-h-0 flex-col rounded-[28px] border border-white/8 p-4">
      <div className="flex flex-col gap-3 border-b border-white/8 pb-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-200/70">Contract Evidence Mapping</p>
          <h2 className="mt-1 font-display text-xl text-white">合同原件区</h2>
          <p className="mt-2 text-sm text-slate-300">左侧按页跳转，右侧连续预览原文。滚动大图时左侧页码会自动跟随。</p>
        </div>

        <div className="flex items-center gap-2 self-start rounded-full border border-white/10 bg-white/[0.03] p-1.5">
          <button
            type="button"
            onClick={() => setZoom((current) => Math.max(0.72, current - 0.08))}
            className="rounded-full p-2 text-slate-300 transition hover:bg-white/8 hover:text-white"
          >
            <Minus className="h-4 w-4" />
          </button>
          <span className="min-w-16 text-center text-sm text-slate-200">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            onClick={() => setZoom((current) => Math.min(1.3, current + 0.08))}
            className="rounded-full p-2 text-slate-300 transition hover:bg-white/8 hover:text-white"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-4 grid min-h-0 flex-1 gap-4 xl:grid-cols-[200px_minmax(0,1fr)] xl:overflow-hidden">
        <div className="min-h-0 overflow-hidden">
          <PageThumbnailList pages={pages} activePage={activePage} onSelect={handleSelectPage} />
        </div>

        <div ref={containerRef} className="thin-scrollbar min-h-0 overflow-y-auto overscroll-contain rounded-[24px] border border-white/8 bg-slate-950/30 p-4">
          {activeEvidence ? (
            <div className="mb-4 rounded-2xl border border-cyan-400/18 bg-cyan-400/[0.08] px-4 py-3 text-sm text-cyan-50">
              当前证据位于第 {activeEvidence.page} 页，定位到“{activeEvidence.text.slice(0, 42)}”
            </div>
          ) : null}

          <div className="space-y-5">
            {pages.map((page) => {
              const imageUrl = resolveImageUrl(page.imageUrl);
              const pageHasActiveEvidence = page.evidences.some((item) => item.id === selectedEvidenceId);
              return (
                <section
                  key={page.page}
                  data-page={page.page}
                  ref={(node) => {
                    pageRefs.current[page.page] = node;
                  }}
                  className="overflow-hidden rounded-[28px] border border-cyan-400/16 bg-cyan-400/[0.04] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.18)]"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">Page {page.page}</p>
                      <p className="mt-1 text-sm text-slate-200">第 {page.page} 页</p>
                    </div>
                    {pageHasActiveEvidence ? (
                      <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-100">
                        <SearchCheck className="h-3.5 w-3.5" />
                        当前证据页
                      </div>
                    ) : null}
                  </div>

                  <div className="mx-auto flex justify-center">
                    <div
                      className="document-page relative rounded-[20px] border border-slate-300/70 bg-white shadow-[0_16px_40px_rgba(15,23,42,0.18)]"
                      style={{ width: page.width * zoom, height: page.height * zoom }}
                    >
                      {imageUrl ? (
                        <img src={imageUrl} alt={`合同第 ${page.page} 页`} className="absolute inset-0 h-full w-full rounded-[20px] object-contain" />
                      ) : null}

                      {!imageUrl
                        ? page.blocks.map((block) => (
                            <div
                              key={block.id}
                              className={block.emphasis ? "absolute font-semibold text-slate-800" : "absolute text-[15px] text-slate-700"}
                              style={{
                                left: block.x * zoom,
                                top: block.y * zoom,
                                width: block.width * zoom,
                              }}
                            >
                              {block.text}
                            </div>
                          ))
                        : null}

                      {page.evidences.map((evidence) => (
                        <EvidenceHighlight
                          key={`${evidence.id}-${page.page}-${evidence.segmentIndex}`}
                          evidence={evidence}
                          scale={zoom}
                          active={selectedEvidenceId === evidence.id}
                          onClick={() => onEvidenceClick(evidence)}
                        />
                      ))}
                    </div>
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
