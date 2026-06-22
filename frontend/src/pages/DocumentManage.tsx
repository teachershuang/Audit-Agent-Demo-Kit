import type { BaseDocumentRecord } from "../types/base";

interface DocumentManageProps {
  documents: BaseDocumentRecord[];
  activeDocumentId: string | null;
  metadataLoading: boolean;
  metrics: {
    documents: number;
    activeDocs: number;
    rules: number;
    enabledRules: number;
  };
  onSelect: (docId: string) => Promise<void>;
  onAbolish: (docId: string) => Promise<void>;
  onReplace: (oldDocId: string, newDocId: string) => Promise<void>;
  onRefresh: () => Promise<void>;
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function statusTone(status: string) {
  if (status === "effective") return "border-emerald-300/25 bg-emerald-400/10 text-emerald-100";
  if (status === "superseded") return "border-amber-300/25 bg-amber-400/10 text-amber-100";
  return "border-rose-300/25 bg-rose-400/10 text-rose-100";
}

function statusLabel(status: string) {
  if (status === "effective") return "有效";
  if (status === "superseded") return "已替代";
  if (status === "abolished") return "已废止";
  return status;
}

export function DocumentManage({
  documents,
  activeDocumentId,
  metadataLoading,
  metrics,
  onSelect,
  onAbolish,
  onReplace,
  onRefresh,
}: DocumentManageProps) {
  const currentVersionCount = documents.filter((item) => item.current_version_flag).length;
  const policyCount = documents.filter((item) => item.doc_type === "policy").length;
  const templateCount = documents.filter((item) => item.doc_type === "template").length;
  const sorted = [...documents].sort((left, right) => {
    if (left.current_version_flag !== right.current_version_flag) {
      return left.current_version_flag ? -1 : 1;
    }
    if (left.name !== right.name) {
      return left.name.localeCompare(right.name, "zh-CN");
    }
    return right.effective_ts - left.effective_ts;
  });

  return (
    <div className="glass-panel rounded-[28px] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Document Registry</div>
          <h3 className="mt-2 text-xl font-semibold text-white">文档管理</h3>
        </div>
        <button
          type="button"
          aria-label="刷新文档列表"
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"
          onClick={() => void onRefresh()}
        >
          刷新
        </button>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <SummaryCard label="文档总数" value={documents.length} />
        <SummaryCard label="当前有效版本" value={currentVersionCount} />
        <SummaryCard label="制度文件" value={policyCount} />
        <SummaryCard label="范本总册" value={templateCount} />
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <SummaryCard label="规则总数" value={metrics.rules} />
        <SummaryCard label="启用规则" value={metrics.enabledRules} />
        <SummaryCard label="有效文档" value={metrics.activeDocs} />
        <SummaryCard label="制度库文档" value={metrics.documents} />
      </div>

      <div className="mt-5 grid gap-4">
        {sorted.map((document) => {
          const active = activeDocumentId === document.id;
          return (
            <div
              key={document.id}
              role="button"
              tabIndex={0}
              aria-label={`查看文档 ${document.name}`}
              onClick={() => void onSelect(document.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void onSelect(document.id);
                }
              }}
              className={`rounded-[24px] border p-4 text-left transition ${
                active ? "border-cyan-300/35 bg-cyan-400/[0.08]" : "border-white/10 bg-slate-950/25 hover:border-cyan-400/24"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-lg font-medium text-white">{document.name}</div>
                    <span className={`rounded-full border px-2.5 py-1 text-[11px] ${statusTone(document.status)}`}>
                      {statusLabel(document.status)}
                    </span>
                    {document.current_version_flag ? (
                      <span className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-2.5 py-1 text-[11px] text-cyan-100">
                        当前版本
                      </span>
                    ) : null}
                    {active && metadataLoading ? (
                      <span className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-2.5 py-1 text-[11px] text-cyan-100">
                        加载中
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-2 text-sm text-slate-300">
                    {document.doc_type} / {document.version} / 生效 {document.effective_ts}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                    <span>来源类型 {document.source_kind}</span>
                    <span>模板数 {document.template_count}</span>
                    {document.replaced_by ? <span>替代为 {document.replaced_by}</span> : null}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    aria-label={`废止文档 ${document.name}`}
                    className="rounded-full border border-rose-300/25 bg-rose-400/10 px-3 py-1.5 text-sm text-rose-100"
                    onClick={(event) => {
                      event.stopPropagation();
                      void onAbolish(document.id);
                    }}
                  >
                    废止
                  </button>
                  <ReplaceButton docId={document.id} documentName={document.name} documents={documents} onReplace={onReplace} />
                </div>
              </div>
            </div>
          );
        })}

        {documents.length === 0 ? <div className="text-sm text-slate-300">暂无已入库文档。</div> : null}
      </div>
    </div>
  );
}

function ReplaceButton({
  docId,
  documentName,
  documents,
  onReplace,
}: {
  docId: string;
  documentName: string;
  documents: BaseDocumentRecord[];
  onReplace: (oldDocId: string, newDocId: string) => Promise<void>;
}) {
  return (
    <label className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200">
      <span>替代为</span>
      <select
        aria-label={`为文档 ${documentName} 选择替代版本`}
        className="bg-transparent text-sm text-slate-100 outline-none"
        defaultValue=""
        onChange={(event) => {
          if (event.target.value) {
            void onReplace(docId, event.target.value);
            event.currentTarget.value = "";
          }
        }}
      >
        <option value="">选择文档</option>
        {documents
          .filter((item) => item.id !== docId)
          .map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} / {item.version}
            </option>
          ))}
      </select>
    </label>
  );
}
