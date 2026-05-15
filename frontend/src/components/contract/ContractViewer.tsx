import { motion } from "framer-motion";
import { Minus, Plus, SearchCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getApiBaseUrlSync } from "../../services/api";
import { cn } from "../../lib/cn";
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

export function ContractViewer({
  pages,
  activePage,
  selectedEvidenceId,
  onSelectPage,
  onEvidenceClick,
}: ContractViewerProps) {
  const [zoom, setZoom] = useState(0.78);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    const activeNode = pageRefs.current[activePage];
    if (activeNode) {
      activeNode.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [activePage]);

  const allEvidences = useMemo(() => pages.flatMap((page) => page.evidences), [pages]);
  const activeEvidence = useMemo(
    () =>
      allEvidences.find((evidence) => evidence.id === selectedEvidenceId && evidence.isPrimary) ??
      allEvidences.find((evidence) => evidence.id === selectedEvidenceId) ??
      null,
    [allEvidences, selectedEvidenceId],
  );
  const activeEvidenceSegments = useMemo(
    () =>
      activeEvidence
        ? allEvidences
            .filter((evidence) => evidence.id === activeEvidence.id)
            .sort((left, right) => left.segmentIndex - right.segmentIndex)
        : [],
    [activeEvidence, allEvidences],
  );

  const apiBaseUrl = getApiBaseUrlSync();

  return (
    <div className="glass-panel flex h-full min-h-[720px] flex-col rounded-[28px] border border-white/8 p-4">
      <div className="flex flex-col gap-3 border-b border-white/8 pb-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-cyan-200/70">
            Contract Evidence Mapping
          </p>
          <h2 className="mt-1 font-display text-xl text-white">合同原件区</h2>
          <p className="mt-2 text-sm text-slate-300">
            左侧原件区独立滚动。点击右侧章节、条款或关注事项后，会自动跳转到对应页并高亮证据区域。
          </p>
        </div>

        <div className="flex items-center gap-2 self-start rounded-full border border-white/10 bg-white/[0.03] p-1.5">
          <button
            type="button"
            onClick={() => setZoom((current) => Math.max(0.6, current - 0.08))}
            className="rounded-full p-2 text-slate-300 transition hover:bg-white/8 hover:text-white"
          >
            <Minus className="h-4 w-4" />
          </button>
          <span className="min-w-16 text-center text-sm text-slate-200">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            onClick={() => setZoom((current) => Math.min(1.15, current + 0.08))}
            className="rounded-full p-2 text-slate-300 transition hover:bg-white/8 hover:text-white"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-4 grid min-h-0 flex-1 gap-4 xl:grid-cols-[178px_1fr]">
        <div className="min-h-0 overflow-hidden">
          <PageThumbnailList pages={pages} activePage={activePage} onSelect={onSelectPage} />
        </div>

        <div
          ref={containerRef}
          className="thin-scrollbar min-h-0 overflow-y-auto overscroll-contain rounded-[24px] border border-white/8 bg-slate-950/30 p-4"
        >
          {activeEvidence ? (
            <div className="mb-4 rounded-2xl border border-cyan-400/18 bg-cyan-400/[0.08] px-4 py-3 text-sm text-cyan-50">
              {activeEvidenceSegments.length > 1
                ? `当前高亮证据共 ${activeEvidenceSegments.length} 个片段，覆盖第 ${[
                    ...new Set(activeEvidenceSegments.map((item) => item.page)),
                  ].join("、")} 页；当前代表片段位于第 ${activeEvidence.page} 页。`
                : `当前高亮证据位于第 ${activeEvidence.page} 页，定位到“${activeEvidence.text.slice(0, 42)}”。`}
            </div>
          ) : null}

          <div className="mx-auto flex max-w-[980px] flex-col gap-6">
            {pages.map((page) => {
              const scale = zoom;
              return (
                <motion.div
                  key={page.page}
                  ref={(node) => {
                    pageRefs.current[page.page] = node;
                  }}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.28 }}
                  className={cn(
                    "overflow-hidden rounded-[28px] border p-4 shadow-[0_30px_80px_rgba(0,0,0,0.24)]",
                    activePage === page.page
                      ? "border-cyan-400/28 bg-cyan-400/[0.04]"
                      : "border-white/8 bg-white/[0.02]",
                  )}
                >
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">Page {page.page}</p>
                      <p className="mt-1 text-sm text-slate-200">{page.title}</p>
                    </div>
                    {activeEvidenceSegments.some((evidence) => evidence.page === page.page) ? (
                      <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-100">
                        <SearchCheck className="h-3.5 w-3.5" />
                        当前证据页
                      </div>
                    ) : null}
                  </div>

                  <div
                    className="document-page relative mx-auto rounded-[20px] border border-slate-300/70"
                    style={{ width: page.width * scale, height: page.height * scale }}
                  >
                    {page.imageUrl ? (
                      <img
                        src={page.imageUrl.startsWith("http") ? page.imageUrl : `${apiBaseUrl}${page.imageUrl}`}
                        alt={`合同第 ${page.page} 页`}
                        className="absolute inset-0 h-full w-full rounded-[20px] object-contain"
                      />
                    ) : null}

                    {!page.imageUrl
                      ? page.blocks.map((block) => (
                          <div
                            key={block.id}
                            className={cn(
                              "absolute leading-7",
                              block.emphasis ? "font-semibold text-slate-800" : "text-[15px] text-slate-700",
                            )}
                            style={{
                              left: block.x * scale,
                              top: block.y * scale,
                              width: block.width * scale,
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
                        scale={scale}
                        active={selectedEvidenceId === evidence.id}
                        onClick={() => onEvidenceClick(evidence)}
                      />
                    ))}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
