import { CheckCircle2, FileSearch, LoaderCircle, Scale, ScanSearch, ShieldAlert, Stamp, Waypoints, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api, getApiBaseUrlSync } from "../../services/api";
import type { AuditFocus, VerificationItem } from "../../types/audit";
import type { BaseReviewIssue, BaseReviewReport } from "../../types/base";
import type { ContractTask, KnowledgeBaseReviewStep } from "../../types/contract";

function toneForStep(status: KnowledgeBaseReviewStep["status"]) {
  if (status === "completed") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-100";
  if (status === "running") return "border-cyan-400/20 bg-cyan-400/10 text-cyan-100";
  if (status === "failed") return "border-rose-400/20 bg-rose-400/10 text-rose-100";
  return "border-white/10 bg-white/[0.03] text-slate-300";
}

function iconForStep(stepId: string) {
  if (stepId === "classify_contract") return ScanSearch;
  if (stepId === "match_template") return FileSearch;
  if (stepId === "extract_schema") return Waypoints;
  if (stepId === "compare_template") return Scale;
  if (stepId === "retrieve_policy") return Stamp;
  if (stepId === "run_rules") return ShieldAlert;
  if (stepId === "generate_issues") return FileSearch;
  return CheckCircle2;
}

function severityTone(severity: string) {
  if (severity === "must_modify") return "border-rose-300/25 bg-rose-400/10 text-rose-100";
  if (severity === "suggest_modify") return "border-amber-300/25 bg-amber-400/10 text-amber-100";
  return "border-cyan-300/25 bg-cyan-400/10 text-cyan-100";
}

function resolveImageUrl(path: string | null | undefined) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${getApiBaseUrlSync()}${path}`;
}

function IssueCard({ issue }: { issue: BaseReviewIssue }) {
  const imageUrl = resolveImageUrl(issue.preview?.image_url);

  return (
    <article className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-white">{issue.problem}</div>
          <div className="mt-2 text-sm text-slate-300">{issue.clause_location || "系统定位"}</div>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] ${severityTone(issue.severity)}`}>{issue.severity}</span>
      </div>

      <div className="mt-3 text-sm text-slate-200">{issue.suggestion}</div>

      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-400">
        <span>置信度 {Math.round(issue.confidence * 100)}%</span>
        {issue.preview?.page ? <span>第 {issue.preview.page} 页</span> : null}
        {issue.source_rule_name ? <span>{issue.source_rule_name}</span> : null}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-white/8 bg-slate-950/25 p-3">
          {imageUrl ? (
            <img src={imageUrl} alt={issue.problem} className="w-full rounded-2xl border border-white/8 object-contain" />
          ) : (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-400">暂无原文截图</div>
          )}
          {issue.preview?.excerpt ? <div className="mt-3 text-sm text-slate-200">{issue.preview.excerpt}</div> : null}
        </div>

        <div className="rounded-2xl border border-white/8 bg-slate-950/25 p-3 text-sm text-slate-300">
          <div>制度依据：{issue.basis_policy.length > 0 ? issue.basis_policy.join("；") : "未回填"}</div>
          {issue.preview?.clause_title ? <div className="mt-2">命中条款：{issue.preview.clause_title}</div> : null}
          {issue.preview?.fact_label ? <div className="mt-2">命中字段：{issue.preview.fact_label}</div> : null}
          {issue.basis_template ? <div className="mt-2">范本依据：{issue.basis_template}</div> : null}
        </div>
      </div>
    </article>
  );
}

export function KnowledgeBaseReviewPanel({
  task,
  auditFocuses,
  verificationItems,
}: {
  task: ContractTask | null;
  auditFocuses: AuditFocus[];
  verificationItems: VerificationItem[];
}) {
  const state = task?.knowledgeBaseReview ?? null;
  const kbFocuses = auditFocuses.filter((item) => item.focusSource === "knowledge_base_rule_check");
  const kbVerification = verificationItems.filter((item) => item.source === "knowledge_base");
  const [report, setReport] = useState<BaseReviewReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!task?.knowledgeBaseReview || task.knowledgeBaseReview.status !== "completed") {
      setReport(null);
      setReportError(null);
      return;
    }
    const contractId = `contract_${task.taskId}`;
    void (async () => {
      try {
        const nextReport = await api.base.getContractReport(contractId);
        if (!cancelled) {
          setReport(nextReport);
          setReportError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setReport(null);
          setReportError(error instanceof Error ? error.message : "未能加载审查报告");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [task?.taskId, task?.knowledgeBaseReview?.status]);

  if (!task) {
    return (
      <div className="rounded-[22px] border border-dashed border-white/10 bg-white/[0.02] px-5 py-8">
        <div className="text-sm font-medium text-white">等待制度校验</div>
        <div className="mt-2 text-sm text-slate-400">上传合同后在这里查看进度和结果。</div>
      </div>
    );
  }

  return (
    <div id="knowledge-base-review-panel" className="space-y-4">
      <section className="rounded-[22px] border border-cyan-400/16 bg-cyan-400/[0.06] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/70">Knowledge Base Review</div>
            <h3 className="mt-2 text-lg font-semibold text-white">制度底座校验</h3>
            <p className="mt-2 text-sm text-cyan-50/90">{state?.message ?? task.stageDetail ?? "尚未启动制度校验。"}</p>
          </div>
          <div className="min-w-[220px] rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{state?.currentStepLabel ?? "等待开始"}</span>
              <span>{state?.progressPercent ?? 0}%</span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-white/8">
              <div
                className="h-2 rounded-full bg-gradient-to-r from-cyan-400 to-sky-300 transition-all duration-500"
                style={{ width: `${state?.progressPercent ?? 0}%` }}
              />
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">识别类别</div>
            <div className="mt-2 text-sm text-white">{state?.detectedCategory ?? "识别中"}</div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">匹配范本</div>
            <div className="mt-2 text-sm text-white">{state?.matchedTemplateName ?? "未匹配到对应有效范本"}</div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">发现问题</div>
            <div className="mt-2 text-sm text-white">{state?.issueCount ?? report?.issues.length ?? kbFocuses.length}</div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        {(state?.steps ?? []).map((step) => {
          const Icon = iconForStep(step.id);
          const statusText =
            step.status === "completed" ? "已完成" : step.status === "running" ? "处理中" : step.status === "failed" ? "失败" : "待执行";
          return (
            <div key={step.id} className={`rounded-[22px] border px-4 py-4 ${toneForStep(step.status)}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="rounded-full border border-white/10 bg-slate-950/25 p-2">
                    {step.status === "running" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">{step.label}</div>
                    <div className="mt-1 text-xs text-slate-300">{statusText}</div>
                  </div>
                </div>
                {step.status === "completed" ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-200" />
                ) : step.status === "failed" ? (
                  <XCircle className="h-4 w-4 text-rose-200" />
                ) : null}
              </div>
              {step.detail ? <div className="mt-3 text-sm text-slate-200">{step.detail}</div> : null}
            </div>
          );
        })}
      </section>

      {state?.status === "completed" ? (
        <section id="knowledge-base-review-result" className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/70">Review Result</div>
              <h4 className="mt-2 text-lg font-semibold text-white">审查报告预览</h4>
              <div className="mt-2 text-sm text-slate-300">
                制度命中问题 {report?.issues.length ?? kbFocuses.length} 条，校验项 {kbVerification.length} 条。
              </div>
            </div>
          </div>

          {reportError ? <div className="mt-4 text-sm text-rose-200">{reportError}</div> : null}

          {report ? (
            <div className="mt-4 space-y-4">
              <div className="rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3 text-sm text-slate-200">
                <div>类别：{report.detected_category}</div>
                <div className="mt-2">范本：{report.matched_template?.template_name ?? "未匹配到对应有效范本"}</div>
                <div className="mt-2 text-slate-300">{report.summary}</div>
              </div>
              {report.issues.slice(0, 8).map((issue) => (
                <IssueCard key={issue.id} issue={issue} />
              ))}
            </div>
          ) : (
            <div className="mt-4 text-sm text-slate-400">正在加载审查报告。</div>
          )}
        </section>
      ) : null}
    </div>
  );
}
