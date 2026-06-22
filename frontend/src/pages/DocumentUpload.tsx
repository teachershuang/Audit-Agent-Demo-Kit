import type { BaseDocumentRecord, BaseRuleRecord } from "../types/base";

interface DocumentUploadProps {
  busy: boolean;
  uploadResult: { document: BaseDocumentRecord; clauseCount: number; rules: BaseRuleRecord[] } | null;
  onSubmit: (payload: {
    file: File;
    docType: string;
    version: string;
    issuer: string;
    category: string;
    effectiveTs: number;
  }) => Promise<void>;
}

export function DocumentUpload({ busy, uploadResult, onSubmit }: DocumentUploadProps) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.15fr]">
      <DocumentUploadForm busy={busy} onSubmit={onSubmit} />
      <div className="glass-panel rounded-[28px] p-5">
        <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Ingestion Result</div>
        <h3 className="mt-2 text-xl font-semibold text-white">入库结果</h3>
        {!uploadResult ? null : (
          <div className="mt-4 space-y-4 text-sm text-slate-200">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <div>文档：{uploadResult.document.name}</div>
              <div className="mt-1 text-slate-300">类型：{uploadResult.document.doc_type}</div>
              <div className="mt-1 text-slate-300">条款：{uploadResult.clauseCount}</div>
              <div className="mt-1 text-slate-300">规则草案：{uploadResult.rules.length}</div>
            </div>
            <div className="space-y-3">
              {uploadResult.rules.slice(0, 8).map((rule) => (
                <div key={rule.id} className="rounded-2xl border border-white/10 bg-slate-950/25 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium text-white">{rule.name}</div>
                    <span className="rounded-full border border-amber-300/20 bg-amber-400/10 px-2 py-1 text-[11px] text-amber-100">
                      {rule.status}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-slate-300">{rule.id}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DocumentUploadForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (payload: {
    file: File;
    docType: string;
    version: string;
    issuer: string;
    category: string;
    effectiveTs: number;
  }) => Promise<void>;
}) {
  return (
    <form
      className="glass-panel rounded-[28px] p-5"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const file = form.get("file");
        if (!(file instanceof File) || !file.size) return;
        void onSubmit({
          file,
          docType: String(form.get("docType") || "policy"),
          version: String(form.get("version") || "v1"),
          issuer: String(form.get("issuer") || ""),
          category: String(form.get("category") || ""),
          effectiveTs: Number(form.get("effectiveTs") || 0),
        });
      }}
    >
      <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Document Upload</div>
      <h3 className="mt-2 text-xl font-semibold text-white">制度 / 范本上传</h3>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="space-y-2 text-sm text-slate-200">
          <span>文件</span>
          <input name="file" type="file" accept=".pdf,.docx" className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3" />
        </label>
        <label className="space-y-2 text-sm text-slate-200">
          <span>类型</span>
          <select name="docType" defaultValue="policy" className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3">
            <option value="policy">制度</option>
            <option value="template">范本总册</option>
          </select>
        </label>
        <label className="space-y-2 text-sm text-slate-200">
          <span>版本</span>
          <input name="version" defaultValue="v1" className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3" />
        </label>
        <label className="space-y-2 text-sm text-slate-200">
          <span>发布机构</span>
          <input name="issuer" defaultValue="黑龙江省交通投资集团有限公司" className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3" />
        </label>
        <label className="space-y-2 text-sm text-slate-200">
          <span>分类</span>
          <input name="category" placeholder="如：合同审核制度 / 合同标准模板" className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3" />
        </label>
        <label className="space-y-2 text-sm text-slate-200">
          <span>生效日期戳</span>
          <input name="effectiveTs" type="number" defaultValue={20250101} className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3" />
        </label>
      </div>
      <button type="submit" disabled={busy} className="mt-5 rounded-full border border-cyan-400/30 bg-cyan-400/12 px-5 py-2.5 text-sm font-medium text-cyan-50 disabled:opacity-50">
        {busy ? "上传中..." : "上传并入库"}
      </button>
    </form>
  );
}
