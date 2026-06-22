import { useEffect, useMemo, useState } from "react";
import { api } from "../services/api";
import type {
  ApiHealth,
  BaseClauseRecord,
  BaseClauseMetadata,
  BaseContractSchema,
  BaseDocumentMetadata,
  BaseDocumentRecord,
  BaseReviewReport,
  BaseRuleMetadata,
  BaseRuleRecord,
  SourceTaskSummary,
} from "../types/base";
import { BaseMetadataPanel } from "./BaseMetadataPanel";
import { ContractReview } from "./ContractReview";
import { DocumentManage } from "./DocumentManage";
import { DocumentUpload } from "./DocumentUpload";
import { ReviewReport } from "./ReviewReport";
import { RuleManage } from "./RuleManage";

type BasePage = "upload" | "documents" | "rules" | "review" | "report";

const pages: Array<{ id: BasePage; label: string }> = [
  { id: "upload", label: "制度上传" },
  { id: "documents", label: "制度管理" },
  { id: "rules", label: "规则管理" },
  { id: "review", label: "合同审查" },
  { id: "report", label: "审查报告" },
];

const pageMessages: Record<BasePage, string> = {
  upload: "上传制度、范本或审查依据文件，进入统一知识底座。",
  documents: "查看版本、模板目录、来源条款和关联规则。",
  rules: "查看、启用和编辑规则草案与映射关系。",
  review: "选择已完成解析的合同任务，发起制度比对与规则审查。",
  report: "查看结构化字段、问题、依据与建议动作。",
};

export function BaseWorkspace({ refreshToken = 0 }: { refreshToken?: number }) {
  const [page, setPage] = useState<BasePage>("upload");
  const [busy, setBusy] = useState(false);
  const [metadataLoading, setMetadataLoading] = useState(false);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const [activeRuleId, setActiveRuleId] = useState<string | null>(null);
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [documents, setDocuments] = useState<BaseDocumentRecord[]>([]);
  const [rules, setRules] = useState<BaseRuleRecord[]>([]);
  const [tasks, setTasks] = useState<SourceTaskSummary[]>([]);
  const [schema, setSchema] = useState<BaseContractSchema | null>(null);
  const [report, setReport] = useState<BaseReviewReport | null>(null);
  const [documentMetadata, setDocumentMetadata] = useState<BaseDocumentMetadata | null>(null);
  const [documentClausesLoading, setDocumentClausesLoading] = useState(false);
  const [clauseMetadata, setClauseMetadata] = useState<BaseClauseMetadata | null>(null);
  const [ruleMetadata, setRuleMetadata] = useState<BaseRuleMetadata | null>(null);
  const [uploadResult, setUploadResult] = useState<{
    document: BaseDocumentRecord;
    clauseCount: number;
    rules: BaseRuleRecord[];
  } | null>(null);
  const [message, setMessage] = useState(pageMessages.upload);

  const metrics = useMemo(
    () => ({
      documents: documents.length,
      activeDocs: documents.filter((item) => item.status === "effective").length,
      rules: rules.length,
      enabledRules: rules.filter((item) => item.enabled).length,
    }),
    [documents, rules],
  );

  function switchPage(nextPage: BasePage) {
    setPage(nextPage);
    setMessage(pageMessages[nextPage]);
    setDocumentMetadata(null);
    setClauseMetadata(null);
    setRuleMetadata(null);
    setActiveDocumentId(null);
    setActiveRuleId(null);
  }

  async function refreshAll() {
    const [nextDocuments, nextRules, nextTasks, nextHealth] = await Promise.all([
      api.base.listDocuments(),
      api.base.listRules(),
      api.base.listSourceTasks(),
      api.getHealth(),
    ]);
    setDocuments(nextDocuments);
    setRules(nextRules);
    setTasks(nextTasks);
    setHealth(nextHealth);
  }

  useEffect(() => {
    void refreshAll();
  }, [refreshToken]);

  async function withBusy(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  async function openDocumentMetadata(docId: string) {
    setMetadataLoading(true);
    setActiveDocumentId(docId);
    setActiveRuleId(null);
    try {
      const metadata = await api.base.getDocumentMetadata(docId, false);
      setDocumentMetadata(metadata);
      setClauseMetadata(null);
      setRuleMetadata(null);
      setMessage(`已打开制度：${metadata.document.name}`);
    } finally {
      setMetadataLoading(false);
    }
  }

  async function loadDocumentClauses(docId: string) {
    if (!documentMetadata || documentMetadata.document.id !== docId || documentMetadata.clauses.length > 0) {
      return;
    }
    setDocumentClausesLoading(true);
    try {
      const clauses: BaseClauseRecord[] = await api.base.getDocumentClauses(docId);
      setDocumentMetadata((current) => (current && current.document.id === docId ? { ...current, clauses } : current));
    } finally {
      setDocumentClausesLoading(false);
    }
  }

  async function openClauseMetadata(clauseId: string) {
    setMetadataLoading(true);
    try {
      const metadata = await api.base.getClauseMetadata(clauseId);
      setClauseMetadata(metadata);
      setDocumentMetadata(null);
      setRuleMetadata(null);
      setMessage(`已打开条款：${metadata.clause.title}`);
    } finally {
      setMetadataLoading(false);
    }
  }

  async function openRuleMetadata(ruleId: string) {
    setMetadataLoading(true);
    setActiveRuleId(ruleId);
    setActiveDocumentId(null);
    try {
      const metadata = await api.base.getRuleMetadata(ruleId);
      setRuleMetadata(metadata);
      setDocumentMetadata(null);
      setClauseMetadata(null);
      setMessage(`已打开规则：${metadata.rule.name}`);
    } finally {
      setMetadataLoading(false);
    }
  }

  return (
    <div className="grid-line min-h-screen px-5 py-5 text-slate-100 md:px-6 xl:px-8">
      <div className="mx-auto w-full max-w-[1680px] space-y-4">
        <header className="glass-panel rounded-[28px] px-5 py-5">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.28em] text-cyan-200/70">Policy Intelligence Base</div>
              <h1 className="mt-2 font-display text-3xl text-white">通用制度智能底座</h1>
              <p className="mt-3 text-sm text-cyan-100/80">{message}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                  审查模型 {health?.llm_model ?? "检测中"}
                </span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                  多模态 {health?.vision_model ?? "检测中"}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {pages.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => switchPage(item.id)}
                  className={`rounded-full px-4 py-2 text-sm ${
                    page === item.id
                      ? "border border-cyan-400/30 bg-cyan-400/12 text-cyan-50"
                      : "border border-white/10 bg-white/5 text-slate-200"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </header>

        {page === "upload" ? (
          <DocumentUpload
            busy={busy}
            uploadResult={uploadResult}
            onSubmit={async ({ file, docType, version, issuer, category, effectiveTs }) => {
              await withBusy(async () => {
                const result = await api.base.uploadDocument({
                  file,
                  docType,
                  version,
                  issuer,
                  category,
                  effectiveTs,
                });
                setUploadResult(result);
                setMessage(`已入库：${result.document.name}`);
                await refreshAll();
              });
            }}
          />
        ) : null}

        {page === "documents" ? (
          <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <DocumentManage
              documents={documents}
              activeDocumentId={activeDocumentId}
              metadataLoading={metadataLoading}
              metrics={metrics}
              onSelect={openDocumentMetadata}
              onRefresh={refreshAll}
              onAbolish={async (docId) => {
                await withBusy(async () => {
                  await api.base.abolishDocument(docId);
                  setMessage(`已废止制度：${docId}`);
                  await refreshAll();
                });
              }}
              onReplace={async (oldDocId, newDocId) => {
                await withBusy(async () => {
                  await api.base.replaceDocument(oldDocId, newDocId);
                  setMessage(`已将 ${oldDocId} 替换为 ${newDocId}`);
                  await refreshAll();
                });
              }}
            />
            <BaseMetadataPanel
              loading={metadataLoading}
              clausesLoading={documentClausesLoading}
              documentMetadata={documentMetadata}
              clauseMetadata={clauseMetadata}
              ruleMetadata={ruleMetadata}
              onPatchDocument={async (docId, payload) => {
                await withBusy(async () => {
                  await api.base.patchDocument(docId, payload);
                  await openDocumentMetadata(docId);
                  await refreshAll();
                });
              }}
              onPatchRule={async (ruleId, payload) => {
                await withBusy(async () => {
                  await api.base.patchRule(ruleId, payload);
                  await openRuleMetadata(ruleId);
                  await refreshAll();
                });
              }}
              onSelectDocument={(docId) => void openDocumentMetadata(docId)}
              onLoadDocumentClauses={(docId) => void loadDocumentClauses(docId)}
              onSelectClause={(clauseId) => void openClauseMetadata(clauseId)}
              onSelectRule={(ruleId) => void openRuleMetadata(ruleId)}
            />
          </div>
        ) : null}

        {page === "rules" ? (
          <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
            <RuleManage
              rules={rules}
              activeRuleId={activeRuleId}
              metadataLoading={metadataLoading}
              onSelect={openRuleMetadata}
              onRefresh={refreshAll}
              onToggle={async (rule) => {
                await withBusy(async () => {
                  await api.base.patchRule(rule.id, { enabled: !rule.enabled });
                  setMessage(`${rule.name} 已${rule.enabled ? "停用" : "启用"}`);
                  await refreshAll();
                  await openRuleMetadata(rule.id);
                });
              }}
            />
            <BaseMetadataPanel
              loading={metadataLoading}
              clausesLoading={documentClausesLoading}
              documentMetadata={documentMetadata}
              clauseMetadata={clauseMetadata}
              ruleMetadata={ruleMetadata}
              onPatchDocument={async (docId, payload) => {
                await withBusy(async () => {
                  await api.base.patchDocument(docId, payload);
                  await openDocumentMetadata(docId);
                  await refreshAll();
                });
              }}
              onPatchRule={async (ruleId, payload) => {
                await withBusy(async () => {
                  await api.base.patchRule(ruleId, payload);
                  await openRuleMetadata(ruleId);
                  await refreshAll();
                });
              }}
              onSelectDocument={(docId) => void openDocumentMetadata(docId)}
              onLoadDocumentClauses={(docId) => void loadDocumentClauses(docId)}
              onSelectClause={(clauseId) => void openClauseMetadata(clauseId)}
              onSelectRule={(ruleId) => void openRuleMetadata(ruleId)}
            />
          </div>
        ) : null}

        {page === "review" ? (
          <ContractReview
            tasks={tasks}
            busy={busy}
            onReview={async ({ sourceTaskId, selectedTemplateId }) => {
              await withBusy(async () => {
                const reviewTask = await api.base.startReviewContract({ sourceTaskId, selectedTemplateId });
                setMessage(reviewTask.message);
                let currentTask = reviewTask;
                while (currentTask.status === "queued" || currentTask.status === "running") {
                  await new Promise((resolve) => window.setTimeout(resolve, 2500));
                  currentTask = await api.base.getReviewTask(reviewTask.task_id);
                  setMessage(currentTask.message);
                }
                if (currentTask.status !== "completed" || !currentTask.contract_id) {
                  throw new Error(currentTask.error || currentTask.message || "审查任务未成功完成");
                }
                const [nextSchema, nextReport] = await Promise.all([
                  api.base.getContractSchema(currentTask.contract_id),
                  api.base.getContractReport(currentTask.contract_id),
                ]);
                setSchema(nextSchema);
                setReport(nextReport);
                switchPage("report");
                setMessage(`审查完成，共 ${currentTask.issue_count ?? nextReport.issues.length} 个问题。`);
              });
            }}
          />
        ) : null}

        {page === "report" ? <ReviewReport schema={schema} report={report} /> : null}
      </div>
    </div>
  );
}
