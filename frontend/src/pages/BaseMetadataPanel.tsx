import { useEffect, useMemo, useState } from "react";
import type {
  BaseClauseMetadata,
  BaseDocumentMetadata,
  BaseDocumentRecord,
  BaseRuleMetadata,
  TemplateCatalogItem,
} from "../types/base";
import { getApiBaseUrlSync } from "../services/api";

interface BaseMetadataPanelProps {
  loading?: boolean;
  clausesLoading?: boolean;
  documentMetadata: BaseDocumentMetadata | null;
  clauseMetadata: BaseClauseMetadata | null;
  ruleMetadata: BaseRuleMetadata | null;
  onPatchDocument?: (docId: string, payload: Record<string, unknown>) => Promise<void>;
  onPatchRule?: (ruleId: string, payload: Record<string, unknown>) => Promise<void>;
  onSelectDocument?: (docId: string) => void;
  onLoadDocumentClauses?: (docId: string) => void;
  onSelectClause?: (clauseId: string) => void;
  onSelectRule?: (ruleId: string) => void;
}

interface TemplatePreviewState {
  documentId: string;
  template: TemplateCatalogItem;
}

function SectionTitle({ children }: { children: string }) {
  return <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">{children}</div>;
}

function SummaryChip({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "accent";
}) {
  return (
    <div
      className={`rounded-2xl border px-3 py-3 ${
        tone === "accent" ? "border-cyan-400/20 bg-cyan-400/[0.07]" : "border-white/10 bg-white/[0.03]"
      }`}
    >
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{label}</div>
      <div className="mt-1 text-sm font-medium text-white">{value}</div>
    </div>
  );
}

function StatusBadge({ document }: { document: BaseDocumentRecord }) {
  const tone =
    document.status === "effective"
      ? "border-emerald-300/25 bg-emerald-400/10 text-emerald-100"
      : document.status === "superseded"
        ? "border-amber-300/25 bg-amber-400/10 text-amber-100"
        : "border-rose-300/25 bg-rose-400/10 text-rose-100";
  return (
    <span className={`rounded-full border px-2.5 py-1 text-[11px] ${tone}`}>
      {document.status}
      {document.current_version_flag ? " / 当前版本" : ""}
    </span>
  );
}

function resolveAssetUrl(path: string | null | undefined) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${getApiBaseUrlSync()}${path}`;
}

function buildPageImageUrl(documentId: string, page: number) {
  return resolveAssetUrl(`/api/base/documents/${documentId}/pages/${page}/image`);
}

function JsonDisclosure({ title, data }: { title: string; data: unknown }) {
  return (
    <details className="rounded-2xl border border-white/10 bg-slate-950/20">
      <summary className="cursor-pointer px-4 py-3 text-sm text-slate-200">{title}</summary>
      <pre className="overflow-auto border-t border-white/8 px-4 py-3 text-xs leading-6 text-slate-300">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

function PreviewImage({
  imageUrl,
  title,
  boxes,
  pageWidth,
  pageHeight,
  className = "max-h-[420px]",
}: {
  imageUrl?: string | null;
  title: string;
  boxes?: Array<{ x0: number; y0: number; x1: number; y1: number }> | null;
  pageWidth?: number | null;
  pageHeight?: number | null;
  className?: string;
}) {
  const resolved = resolveAssetUrl(imageUrl);
  if (!resolved) return null;
  return (
    <div className={`relative overflow-hidden rounded-2xl border border-white/8 bg-slate-950/25 ${className}`}>
      <img src={resolved} alt={title} className="h-full w-full object-contain" />
      {boxes?.length && pageWidth && pageHeight ? (
        <div className="pointer-events-none absolute inset-0">
          {boxes.map((box, index) => (
            <div
              key={`${box.x0}:${box.y0}:${index}`}
              className="absolute rounded-md border border-cyan-300/90 bg-cyan-300/10"
              style={{
                left: `${(box.x0 / pageWidth) * 100}%`,
                top: `${(box.y0 / pageHeight) * 100}%`,
                width: `${((box.x1 - box.x0) / pageWidth) * 100}%`,
                height: `${((box.y1 - box.y0) / pageHeight) * 100}%`,
              }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function TemplatePreviewModal({
  state,
  onClose,
}: {
  state: TemplatePreviewState;
  onClose: () => void;
}) {
  const [currentPage, setCurrentPage] = useState(state.template.preview_page ?? state.template.start_page);
  const [fullScreen, setFullScreen] = useState(false);
  const pages = useMemo(
    () =>
      Array.from(
        { length: state.template.end_page - state.template.start_page + 1 },
        (_, index) => state.template.start_page + index,
      ),
    [state.template.end_page, state.template.start_page],
  );

  useEffect(() => {
    setCurrentPage(state.template.preview_page ?? state.template.start_page);
    setFullScreen(false);
  }, [state.template.preview_page, state.template.start_page, state.template.template_id]);

  const imageUrl = buildPageImageUrl(state.documentId, currentPage);

  return (
    <div className={`fixed inset-0 z-50 bg-slate-950/80 ${fullScreen ? "p-0" : "p-6"}`}>
      <div
        className={`mx-auto flex h-full flex-col overflow-hidden border border-cyan-400/20 bg-[#0b1523] shadow-2xl ${
          fullScreen ? "w-full rounded-none" : "max-w-[1560px] rounded-[28px]"
        }`}
      >
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/8 px-5 py-4">
          <div className="min-w-0">
            <div className="text-lg font-semibold text-white">{state.template.template_name}</div>
            <div className="mt-1 text-sm text-slate-300">
              仅预览自动切分后的模板页范围：第 {state.template.start_page}-{state.template.end_page} 页
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-300">
              {state.template.usage_profile ? (
                <span className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1 text-cyan-100">
                  用途画像：{state.template.usage_profile}
                </span>
              ) : null}
              {state.template.disambiguation_label ? (
                <span className="rounded-full border border-amber-300/24 bg-amber-400/10 px-3 py-1 text-amber-100">
                  {state.template.disambiguation_label}
                </span>
              ) : null}
            </div>
            {state.template.usage_profile_summary ? (
              <div className="mt-2 text-xs text-cyan-100/80">{state.template.usage_profile_summary}</div>
            ) : null}
            {state.template.auto_variant_summary ? (
              <div className="mt-1 text-xs text-amber-100/80">{state.template.auto_variant_summary}</div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFullScreen((current) => !current)}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"
            >
              {fullScreen ? "退出全屏" : "全屏预览"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 gap-4 p-5 xl:grid-cols-[280px_1fr]">
          <div className="min-h-0 overflow-auto rounded-2xl border border-white/8 bg-white/[0.02] p-3">
            <SectionTitle>页码导航</SectionTitle>
            <div className="space-y-2">
              {pages.map((page) => {
                const pageImageUrl = buildPageImageUrl(state.documentId, page);
                return (
                  <button
                    key={page}
                    type="button"
                    onClick={() => setCurrentPage(page)}
                    className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                      currentPage === page
                        ? "border-cyan-300/35 bg-cyan-400/[0.08]"
                        : "border-white/8 bg-slate-950/20 hover:border-cyan-400/24"
                    }`}
                  >
                    <div className="text-xs text-slate-400">第 {page} 页</div>
                    {pageImageUrl ? (
                      <img
                        src={pageImageUrl}
                        alt={`${state.template.template_name} 第 ${page} 页`}
                        className="mt-2 max-h-36 w-full rounded-xl border border-white/8 object-contain"
                      />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid min-h-0 gap-4 xl:grid-rows-[auto_1fr]">
            <div className="grid gap-3 md:grid-cols-4">
              <SummaryChip label="模板页数" value={pages.length} />
              <SummaryChip label="条款数量" value={state.template.clause_count ?? "-"} />
              <SummaryChip label="当前页面" value={`第 ${currentPage} 页`} tone="accent" />
              <SummaryChip
                label="分类"
                value={[state.template.category_lv1, state.template.category_lv2].filter(Boolean).join(" / ") || "未分类"}
              />
            </div>

            <div className="grid min-h-0 gap-4 xl:grid-cols-[1fr_320px]">
              <div className="min-h-0 overflow-auto rounded-2xl border border-white/8 bg-slate-950/25 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="text-sm text-slate-200">切分模板预览</div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={currentPage <= state.template.start_page}
                      onClick={() => setCurrentPage((page) => Math.max(state.template.start_page, page - 1))}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 disabled:opacity-40"
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      disabled={currentPage >= state.template.end_page}
                      onClick={() => setCurrentPage((page) => Math.min(state.template.end_page, page + 1))}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 disabled:opacity-40"
                    >
                      下一页
                    </button>
                  </div>
                </div>
                {imageUrl ? (
                  <img
                    src={imageUrl}
                    alt={`${state.template.template_name} 第 ${currentPage} 页`}
                    className="mx-auto max-h-[calc(100vh-260px)] w-full rounded-2xl border border-white/8 object-contain"
                  />
                ) : (
                  <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-8 text-sm text-slate-300">
                    当前模板页图尚未生成。
                  </div>
                )}
              </div>

              <div className="min-h-0 overflow-auto rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                <SectionTitle>模板画像</SectionTitle>
                <div className="space-y-3 text-sm text-slate-200">
                  <div>
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-400">用途画像</div>
                    <div className="mt-1 text-base font-medium text-white">
                      {state.template.usage_profile ?? "未识别到明确画像"}
                    </div>
                    {state.template.usage_profile_summary ? (
                      <div className="mt-1 text-xs text-cyan-100/80">{state.template.usage_profile_summary}</div>
                    ) : null}
                  </div>

                  {state.template.usage_profile_basis?.length ? (
                    <div>
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400">判定依据</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {state.template.usage_profile_basis.map((item) => (
                          <span
                            key={item}
                            className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-100"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {state.template.auto_variant_cues?.length ? (
                    <div>
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400">同名区分线索</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {state.template.auto_variant_cues.map((item) => (
                          <span
                            key={item}
                            className="rounded-full border border-amber-300/24 bg-amber-400/10 px-3 py-1 text-xs text-amber-100"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {state.template.signature ? (
                    <div>
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400">条款签名</div>
                      <div className="mt-1 text-sm text-slate-300">{state.template.signature}</div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function BaseMetadataPanel({
  loading = false,
  clausesLoading = false,
  documentMetadata,
  clauseMetadata,
  ruleMetadata,
  onPatchDocument,
  onPatchRule,
  onSelectDocument,
  onLoadDocumentClauses,
  onSelectClause,
  onSelectRule,
}: BaseMetadataPanelProps) {
  const [templatePreview, setTemplatePreview] = useState<TemplatePreviewState | null>(null);
  const [editingDocument, setEditingDocument] = useState(false);
  const [editingRule, setEditingRule] = useState(false);
  const [documentDraft, setDocumentDraft] = useState({
    name: "",
    category: "",
    version: "",
    issuer: "",
  });
  const [ruleDraft, setRuleDraft] = useState({
    name: "",
    enabled: false,
    severity: "",
    suggestion_template: "",
  });

  useEffect(() => {
    if (documentMetadata) {
      setEditingDocument(false);
      setDocumentDraft({
        name: documentMetadata.document.name ?? "",
        category: documentMetadata.document.category ?? "",
        version: documentMetadata.document.version ?? "",
        issuer: documentMetadata.document.issuer ?? "",
      });
    }
  }, [documentMetadata]);

  useEffect(() => {
    if (ruleMetadata) {
      setEditingRule(false);
      setRuleDraft({
        name: ruleMetadata.rule.name ?? "",
        enabled: Boolean(ruleMetadata.rule.enabled),
        severity: ruleMetadata.rule.severity ?? "",
        suggestion_template: ruleMetadata.rule.suggestion_template ?? "",
      });
    }
  }, [ruleMetadata]);

  const title = documentMetadata
    ? "来源、规则与定位信息"
    : clauseMetadata
      ? "条款来源与规则关联"
      : ruleMetadata
        ? "规则来源与定位信息"
        : "来源、规则与定位信息";

  return (
    <>
      <div className="glass-panel rounded-[28px] p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Metadata Inspector</div>
            <h3 className="mt-2 text-xl font-semibold text-white">{title}</h3>
          </div>
        </div>

        <div className="mt-5">
          {loading ? (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-6 text-sm text-slate-300">
              正在加载来源信息...
            </div>
          ) : null}

          {!loading && documentMetadata ? (
            <div className="space-y-5">
              <div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-2xl font-semibold text-white">{documentMetadata.document.name}</div>
                    <div className="mt-2 text-sm text-slate-300">
                      {documentMetadata.document.doc_type} / {documentMetadata.document.version} / 生效 {documentMetadata.document.effective_ts}
                    </div>
                    <div className="mt-2 text-xs text-slate-400">来源文件：{documentMetadata.document.source_file}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <StatusBadge document={documentMetadata.document} />
                      {documentMetadata.document.category ? (
                        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
                          {documentMetadata.document.category}
                        </span>
                      ) : null}
                      {documentMetadata.document.source_kind ? (
                        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
                          {documentMetadata.document.source_kind}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {onPatchDocument ? (
                    <button
                      type="button"
                      onClick={() => setEditingDocument((current) => !current)}
                      className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100"
                    >
                      {editingDocument ? "取消编辑" : "编辑文档"}
                    </button>
                  ) : null}
                </div>

                {editingDocument && onPatchDocument ? (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="text-sm text-slate-200">
                      名称
                      <input
                        value={documentDraft.name}
                        onChange={(event) => setDocumentDraft((current) => ({ ...current, name: event.target.value }))}
                        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <label className="text-sm text-slate-200">
                      分类
                      <input
                        value={documentDraft.category}
                        onChange={(event) => setDocumentDraft((current) => ({ ...current, category: event.target.value }))}
                        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <label className="text-sm text-slate-200">
                      版本
                      <input
                        value={documentDraft.version}
                        onChange={(event) => setDocumentDraft((current) => ({ ...current, version: event.target.value }))}
                        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <label className="text-sm text-slate-200">
                      发布机构
                      <input
                        value={documentDraft.issuer}
                        onChange={(event) => setDocumentDraft((current) => ({ ...current, issuer: event.target.value }))}
                        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <div className="md:col-span-2">
                      <button
                        type="button"
                        onClick={() =>
                          void onPatchDocument(documentMetadata.document.id, {
                            name: documentDraft.name,
                            category: documentDraft.category || null,
                            version: documentDraft.version,
                            issuer: documentDraft.issuer || null,
                          })
                        }
                        className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100"
                      >
                        保存文档
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="grid gap-3 md:grid-cols-4">
                <SummaryChip label="条款总数" value={documentMetadata.summary?.clause_count ?? 0} />
                <SummaryChip label="生效条款" value={documentMetadata.summary?.effective_clause_count ?? 0} />
                <SummaryChip label="关联规则" value={documentMetadata.summary?.rule_count ?? 0} />
                <SummaryChip
                  label="模板目录"
                  value={documentMetadata.summary?.template_count ?? documentMetadata.document.template_catalog.length}
                  tone="accent"
                />
              </div>

              {documentMetadata.version_context?.same_series?.length ? (
                <div>
                  <SectionTitle>版本链</SectionTitle>
                  <div className="space-y-2">
                    {documentMetadata.version_context.same_series.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => onSelectDocument?.(item.id)}
                        className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left transition hover:border-cyan-400/24"
                      >
                        <div>
                          <div className="font-medium text-white">{item.name}</div>
                          <div className="mt-1 text-xs text-slate-400">
                            {item.version} / 生效 {item.effective_ts}
                          </div>
                        </div>
                        <StatusBadge document={item} />
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {documentMetadata.document.template_catalog.length ? (
                <div>
                  <SectionTitle>模板目录</SectionTitle>
                  <div className="space-y-3">
                    {documentMetadata.document.template_catalog.map((item) => (
                      <button
                        key={`${item.template_id}:${item.start_page}:${item.end_page}`}
                        type="button"
                        onClick={() =>
                          setTemplatePreview({
                            documentId: documentMetadata.document.id,
                            template: item,
                          })
                        }
                        className="w-full rounded-[24px] border border-cyan-400/12 bg-cyan-400/[0.05] px-4 py-4 text-left transition hover:border-cyan-300/30"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-lg font-medium text-white">{item.template_name}</div>
                            <div className="mt-1 text-sm text-slate-300">
                              {[item.category_lv1, item.category_lv2].filter(Boolean).join(" / ") || "未分类"}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2 text-xs">
                              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-slate-300">
                                第 {item.start_page}-{item.end_page} 页
                              </span>
                              {item.clause_count != null ? (
                                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-slate-300">
                                  条款 {item.clause_count}
                                </span>
                              ) : null}
                              {item.usage_profile ? (
                                <span className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1 text-cyan-100">
                                  {item.usage_profile}
                                </span>
                              ) : null}
                            </div>
                            {item.usage_profile_summary ? (
                              <div className="mt-2 text-xs text-cyan-100/80">{item.usage_profile_summary}</div>
                            ) : null}
                            {item.auto_variant_summary ? (
                              <div className="mt-1 text-xs text-amber-100/80">{item.auto_variant_summary}</div>
                            ) : null}
                            {item.signature ? <div className="mt-2 text-xs text-slate-400">条款签名：{item.signature}</div> : null}
                          </div>
                          <div className="h-28 w-24 overflow-hidden rounded-2xl border border-white/8 bg-slate-950/25">
                            {buildPageImageUrl(documentMetadata.document.id, item.preview_page ?? item.start_page) ? (
                              <img
                                src={buildPageImageUrl(documentMetadata.document.id, item.preview_page ?? item.start_page) ?? ""}
                                alt={item.template_name}
                                className="h-full w-full object-contain"
                              />
                            ) : null}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <SectionTitle>条款列表</SectionTitle>
                  {documentMetadata.clauses.length === 0 && onLoadDocumentClauses ? (
                    <button
                      type="button"
                      onClick={() => onLoadDocumentClauses(documentMetadata.document.id)}
                      className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"
                    >
                      {clausesLoading ? "正在加载条款..." : "加载条款"}
                    </button>
                  ) : null}
                </div>
                {documentMetadata.clauses.length ? (
                  <div className="space-y-3">
                    {documentMetadata.clauses.map((clause) => (
                      <button
                        key={clause.id}
                        type="button"
                        onClick={() => onSelectClause?.(clause.id)}
                        className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left transition hover:border-cyan-400/24"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="font-medium text-white">{clause.title}</div>
                          <div className="text-xs text-slate-400">
                            第 {clause.page_start}-{clause.page_end} 页
                          </div>
                        </div>
                        <div className="mt-2 text-sm text-slate-300">{clause.content}</div>
                      </button>
                    ))}
                  </div>
                ) : !clausesLoading ? (
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-6 text-sm text-slate-300">
                    当前先返回轻量 metadata。点击“加载条款”后再查看条款明细。
                  </div>
                ) : null}
              </div>

              {documentMetadata.rules.length ? (
                <div>
                  <SectionTitle>关联规则</SectionTitle>
                  <div className="space-y-3">
                    {documentMetadata.rules.map((rule) => (
                      <button
                        key={rule.id}
                        type="button"
                        onClick={() => onSelectRule?.(rule.id)}
                        className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left transition hover:border-cyan-400/24"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="font-medium text-white">{rule.name}</div>
                          <div className="text-xs text-slate-400">
                            {rule.department} / {rule.severity} / {rule.enabled ? "已启用" : "未启用"}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {!loading && clauseMetadata ? (
            <div className="space-y-5">
              <div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
                <div className="text-2xl font-semibold text-white">{clauseMetadata.clause.title}</div>
                <div className="mt-2 text-sm text-slate-300">
                  {clauseMetadata.summary?.category_path || clauseMetadata.summary?.template_name || "条款明细"}
                </div>
                <div className="mt-2 text-xs text-slate-400">
                  第 {clauseMetadata.clause.page_start}-{clauseMetadata.clause.page_end} 页 / {clauseMetadata.clause.status}
                </div>
              </div>

              {clauseMetadata.clause.preview ? (
                <PreviewImage
                  imageUrl={clauseMetadata.clause.preview.image_url}
                  title={clauseMetadata.clause.title}
                  boxes={clauseMetadata.clause.preview.boxes}
                  pageWidth={clauseMetadata.clause.preview.page_width}
                  pageHeight={clauseMetadata.clause.preview.page_height}
                />
              ) : null}

              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4 text-sm leading-7 text-slate-200">
                {clauseMetadata.clause.content}
              </div>

              {clauseMetadata.linked_rules.length ? (
                <div>
                  <SectionTitle>关联规则</SectionTitle>
                  <div className="space-y-3">
                    {clauseMetadata.linked_rules.map((rule) => (
                      <button
                        key={rule.id}
                        type="button"
                        onClick={() => onSelectRule?.(rule.id)}
                        className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left transition hover:border-cyan-400/24"
                      >
                        <div className="font-medium text-white">{rule.name}</div>
                        <div className="mt-1 text-xs text-slate-400">
                          {rule.department} / {rule.severity}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {!loading && ruleMetadata ? (
            <div className="space-y-5">
              <div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-2xl font-semibold text-white">{ruleMetadata.rule.name}</div>
                    <div className="mt-2 text-sm text-slate-300">
                      {ruleMetadata.rule.department} / {ruleMetadata.rule.severity} / {ruleMetadata.rule.enabled ? "已启用" : "未启用"}
                    </div>
                  </div>
                  {onPatchRule ? (
                    <button
                      type="button"
                      onClick={() => setEditingRule((current) => !current)}
                      className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100"
                    >
                      {editingRule ? "取消编辑" : "编辑规则"}
                    </button>
                  ) : null}
                </div>

                {editingRule && onPatchRule ? (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <label className="text-sm text-slate-200">
                      规则名称
                      <input
                        value={ruleDraft.name}
                        onChange={(event) => setRuleDraft((current) => ({ ...current, name: event.target.value }))}
                        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <label className="text-sm text-slate-200">
                      严重级别
                      <input
                        value={ruleDraft.severity}
                        onChange={(event) => setRuleDraft((current) => ({ ...current, severity: event.target.value }))}
                        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3 text-sm text-slate-200">
                      <input
                        type="checkbox"
                        checked={ruleDraft.enabled}
                        onChange={(event) => setRuleDraft((current) => ({ ...current, enabled: event.target.checked }))}
                      />
                      启用规则
                    </label>
                    <label className="text-sm text-slate-200 md:col-span-2">
                      建议模板
                      <textarea
                        value={ruleDraft.suggestion_template}
                        onChange={(event) =>
                          setRuleDraft((current) => ({ ...current, suggestion_template: event.target.value }))
                        }
                        className="mt-2 min-h-[110px] w-full rounded-2xl border border-white/10 bg-slate-950/25 px-3 py-2 text-white outline-none"
                      />
                    </label>
                    <div className="md:col-span-2">
                      <button
                        type="button"
                        onClick={() =>
                          void onPatchRule(ruleMetadata.rule.id, {
                            name: ruleDraft.name,
                            enabled: ruleDraft.enabled,
                            severity: ruleDraft.severity,
                            suggestion_template: ruleDraft.suggestion_template,
                          })
                        }
                        className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100"
                      >
                        保存规则
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              {ruleMetadata.source_document ? (
                <div>
                  <SectionTitle>来源文档</SectionTitle>
                  <button
                    type="button"
                    onClick={() => onSelectDocument?.(ruleMetadata.source_document!.id)}
                    className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4 text-left transition hover:border-cyan-400/24"
                  >
                    <div className="font-medium text-white">{ruleMetadata.source_document.name}</div>
                    <div className="mt-1 text-sm text-slate-300">
                      {ruleMetadata.source_document.doc_type} / {ruleMetadata.source_document.version}
                    </div>
                  </button>
                </div>
              ) : null}

              {ruleMetadata.source_clauses.length ? (
                <div>
                  <SectionTitle>来源条款</SectionTitle>
                  <div className="space-y-4">
                    {ruleMetadata.source_clauses.map((clause) => (
                      <div key={clause.id} className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="font-medium text-white">{clause.title}</div>
                          <div className="text-xs text-slate-400">
                            第 {clause.page_start}-{clause.page_end} 页
                          </div>
                        </div>
                        <div className="mt-3 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                          <PreviewImage
                            imageUrl={clause.preview?.image_url}
                            title={clause.title}
                            boxes={clause.preview?.boxes}
                            pageWidth={clause.preview?.page_width}
                            pageHeight={clause.preview?.page_height}
                            className="max-h-[320px]"
                          />
                          <div className="rounded-2xl border border-white/8 bg-slate-950/25 px-4 py-3 text-sm leading-7 text-slate-200">
                            {clause.content}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <JsonDisclosure title="规则逻辑 JSON" data={ruleMetadata.rule.logic} />
            </div>
          ) : null}

          {!loading && !documentMetadata && !clauseMetadata && !ruleMetadata ? (
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-6 text-sm text-slate-300">
              点击左侧文档、条款或规则后，在这里查看来源、规则与定位信息。
            </div>
          ) : null}
        </div>
      </div>

      {templatePreview ? <TemplatePreviewModal state={templatePreview} onClose={() => setTemplatePreview(null)} /> : null}
    </>
  );
}
