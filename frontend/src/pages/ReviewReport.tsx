import { getApiBaseUrlSync } from "../services/api";
import type { BaseContractSchema, BaseReviewIssue, BaseReviewReport } from "../types/base";

interface ReviewReportProps {
  schema: BaseContractSchema | null;
  report: BaseReviewReport | null;
}

const fieldLabels: Record<string, string> = {
  contract_parties: "合同主体",
  unified_social_credit_code: "统一社会信用代码",
  legal_representative: "法定代表人 / 授权代表",
  contract_subject: "合同标的",
  quantity: "数量",
  quality: "质量 / 规格",
  price: "价款",
  tax_rate: "税率 / 含税约定",
  invoice: "发票",
  payment_terms: "付款节点",
  delivery_term: "履行 / 交付期限",
  acceptance_standard: "验收标准",
  breach_liability: "违约责任",
  termination: "解除 / 终止",
  confidentiality: "保密",
  intellectual_property: "知识产权",
  dispute_resolution: "争议解决",
  signing_place: "签署地",
  effectiveness_condition: "生效条件",
  attachments: "附件清单",
};

function severityTone(severity: string) {
  if (severity === "must_modify") return "border-rose-300/25 bg-rose-400/10 text-rose-100";
  if (severity === "suggest_modify") return "border-amber-300/25 bg-amber-400/10 text-amber-100";
  return "border-cyan-300/25 bg-cyan-400/10 text-cyan-100";
}

function resolveImageUrl(path: string | null | undefined) {
  if (!path) return null;
  return path.startsWith("http") ? path : `${getApiBaseUrlSync()}${path}`;
}

function IssuePreviewCard({ issue }: { issue: BaseReviewIssue }) {
  const imageUrl = resolveImageUrl(issue.preview?.image_url);

  return (
    <article className="rounded-[24px] border border-white/10 bg-slate-950/25 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-white">{issue.problem}</div>
          <div className="mt-2 text-sm text-slate-300">{issue.clause_location || "系统定位"}</div>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] ${severityTone(issue.severity)}`}>{issue.severity}</span>
      </div>

      <div className="mt-3 text-sm text-slate-100">{issue.suggestion}</div>

      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-400">
        <span>部门：{issue.department}</span>
        <span>置信度：{Math.round(issue.confidence * 100)}%</span>
        {issue.source_rule_name ? <span>规则：{issue.source_rule_name}</span> : null}
        {issue.preview?.page ? <span>页码：第 {issue.preview.page} 页</span> : null}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
          <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/70">Source Preview</div>
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={issue.preview?.excerpt ?? issue.problem}
              className="mt-3 w-full rounded-2xl border border-white/8 object-contain"
            />
          ) : (
            <div className="mt-3 rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-400">
              暂未生成原文截图。
            </div>
          )}
          {issue.preview?.excerpt ? <div className="mt-3 text-sm text-slate-200">{issue.preview.excerpt}</div> : null}
          {issue.preview?.note ? <div className="mt-2 text-xs text-slate-400">{issue.preview.note}</div> : null}
        </div>

        <div className="space-y-3">
          <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
            <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/70">Basis</div>
            <div className="mt-3 text-sm text-slate-200">
              制度依据：{issue.basis_policy.length > 0 ? issue.basis_policy.join("，") : "未回填"}
            </div>
            {issue.basis_template ? <div className="mt-2 text-sm text-slate-300">范本依据：{issue.basis_template}</div> : null}
          </div>

          {issue.basis_policy_details && issue.basis_policy_details.length > 0 ? (
            <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-3">
              <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/70">Policy Clauses</div>
              <div className="mt-3 space-y-2">
                {issue.basis_policy_details.slice(0, 3).map((item, index) => (
                  <div key={`${issue.id}-policy-${index}`} className="rounded-xl border border-white/8 bg-slate-950/25 p-3 text-sm text-slate-200">
                    <div className="font-medium text-white">{String(item.title ?? `依据条款 ${index + 1}`)}</div>
                    <div className="mt-2 text-slate-300">{String(item.content ?? "")}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function ReviewReport({ schema, report }: ReviewReportProps) {
  if (!schema && !report) {
    return (
      <div className="glass-panel rounded-[28px] p-6 text-sm text-slate-300">
        暂无审查报告。请先发起合同审查。
      </div>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="glass-panel rounded-[28px] p-5">
        <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Contract Schema</div>
        <h3 className="mt-2 text-xl font-semibold text-white">结构化字段</h3>
        {!schema ? (
          <div className="mt-4 text-sm text-slate-400">暂未提取结构化字段。</div>
        ) : (
          <div className="mt-4 grid gap-3">
            {Object.entries(schema.fields).map(([key, value]) => (
              <div key={key} className="rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{fieldLabels[key] ?? key}</div>
                <div className="mt-2 text-sm text-white">{value || "未提取"}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="glass-panel rounded-[28px] p-5">
        <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Review Report</div>
        <h3 className="mt-2 text-xl font-semibold text-white">审查报告</h3>
        {!report ? (
          <div className="mt-4 text-sm text-slate-400">审查已完成，但暂未拉取到报告。</div>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="rounded-[24px] border border-white/10 bg-white/[0.04] p-4 text-sm text-slate-200">
              <div>合同类别：{report.detected_category}</div>
              <div className="mt-2">匹配范本：{report.matched_template?.template_name ?? "未匹配"}</div>
              <div className="mt-2">问题数量：{report.issues.length}</div>
              <div className="mt-3 text-slate-300">{report.summary}</div>
            </div>

            {report.issues.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-400">未发现制度层面问题。</div>
            ) : (
              report.issues.map((issue) => <IssuePreviewCard key={issue.id} issue={issue} />)
            )}
          </div>
        )}
      </section>
    </div>
  );
}
