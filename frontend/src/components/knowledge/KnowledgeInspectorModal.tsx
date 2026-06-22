import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type {
  BaseClauseMetadata,
  BaseDocumentMetadata,
  BaseRuleMetadata,
} from "../../types/base";
import { BaseMetadataPanel } from "../../pages/BaseMetadataPanel";

export interface KnowledgeSelection {
  documentId?: string | null;
  clauseId?: string | null;
  ruleId?: string | null;
}

export function KnowledgeInspectorModal({
  open,
  selection,
  onClose,
}: {
  open: boolean;
  selection: KnowledgeSelection | null;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documentMetadata, setDocumentMetadata] = useState<BaseDocumentMetadata | null>(null);
  const [clauseMetadata, setClauseMetadata] = useState<BaseClauseMetadata | null>(null);
  const [ruleMetadata, setRuleMetadata] = useState<BaseRuleMetadata | null>(null);

  async function loadDocument(docId: string) {
    setLoading(true);
    setError(null);
    try {
      const metadata = await api.base.getDocumentMetadata(docId);
      setDocumentMetadata(metadata);
      setClauseMetadata(null);
      setRuleMetadata(null);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "无法加载文档 metadata");
    } finally {
      setLoading(false);
    }
  }

  async function loadClause(clauseId: string) {
    setLoading(true);
    setError(null);
    try {
      const metadata = await api.base.getClauseMetadata(clauseId);
      setClauseMetadata(metadata);
      setDocumentMetadata(null);
      setRuleMetadata(null);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "无法加载条款 metadata");
    } finally {
      setLoading(false);
    }
  }

  async function loadRule(ruleId: string) {
    setLoading(true);
    setError(null);
    try {
      const metadata = await api.base.getRuleMetadata(ruleId);
      setRuleMetadata(metadata);
      setDocumentMetadata(null);
      setClauseMetadata(null);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "无法加载规则 metadata");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open || !selection) return;
    if (selection.ruleId) {
      void loadRule(selection.ruleId);
      return;
    }
    if (selection.clauseId) {
      void loadClause(selection.clauseId);
      return;
    }
    if (selection.documentId) {
      void loadDocument(selection.documentId);
    }
  }, [open, selection?.documentId, selection?.clauseId, selection?.ruleId]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/78 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-[1120px] flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[#0f1b2d] shadow-[0_30px_120px_rgba(2,8,23,0.55)]">
        <div className="flex items-center justify-between border-b border-white/8 px-5 py-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">Knowledge Inspector</div>
            <h2 className="mt-1 text-xl font-semibold text-white">制度底座依据查看</h2>
            <p className="mt-1 text-sm text-slate-300">查看规则、来源条款、页码定位和关联文档。</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-200 hover:border-cyan-400/24 hover:bg-white/[0.06]"
          >
            关闭
          </button>
        </div>

        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto p-5">
          {loading ? <div className="text-sm text-slate-300">正在加载来源详情...</div> : null}
          {error ? <div className="text-sm text-rose-200">{error}</div> : null}
          {!loading ? (
            <BaseMetadataPanel
              documentMetadata={documentMetadata}
              clauseMetadata={clauseMetadata}
              ruleMetadata={ruleMetadata}
              onSelectDocument={(docId) => void loadDocument(docId)}
              onSelectClause={(clauseId) => void loadClause(clauseId)}
              onSelectRule={(ruleId) => void loadRule(ruleId)}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}
