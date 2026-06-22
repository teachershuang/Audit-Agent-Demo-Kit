import { useMemo, useState } from "react";
import type { ClauseTag } from "../../types/contract";
import { EvidenceButton } from "../shared/EvidenceButton";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";

const fieldLabels: Record<string, string> = {
  totalAmount: "总金额",
  currency: "币种",
  paymentMethod: "付款方式",
  paymentSchedule: "付款计划",
  taxRate: "税率",
  invoiceRequirement: "发票要求",
  performancePeriod: "履行期限",
  deliveryDate: "交付期限",
  acceptanceStandard: "验收标准",
  breachLiability: "违约责任",
  disputeResolution: "争议解决",
  subjectMatter: "合同标的",
  quantity: "数量",
  quality: "质量",
  businessName: "业务名称",
  projectName: "项目名称",
};

function sourceLabel(source: ClauseTag["labelSource"]) {
  if (source === "agent_discovered") return "Agent 新发现";
  if (source === "user_configured") return "人工配置";
  return "核心标签";
}

function toDisplayValue(value: unknown) {
  if (value == null || value === "") return "未填";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

export function ClauseCard({
  clause,
  active,
  editMode,
  onSelect,
  onStructuredFieldChange,
}: {
  clause: ClauseTag;
  active: boolean;
  editMode: boolean;
  onSelect: (clause: ClauseTag) => void;
  onStructuredFieldChange: (patch: { clauseId: string; fieldKey: string; value: unknown }) => void;
}) {
  const [draftInputs, setDraftInputs] = useState<Record<string, string>>({});
  const fields = useMemo(() => Object.entries(clause.structuredFields ?? {}), [clause.structuredFields]);

  return (
    <article
      id={`card-${clause.id}`}
      className={`rounded-[22px] border p-4 transition ${
        active ? "border-cyan-300/40 bg-cyan-400/[0.08]" : "border-white/8 bg-white/[0.03]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">{clause.label}</p>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
              {sourceLabel(clause.labelSource)}
            </span>
          </div>
          <h3 className="mt-1 text-base font-semibold text-white">{clause.title}</h3>
          {clause.sectionTitle ? <p className="mt-1 text-xs text-slate-400">所属章节：{clause.sectionTitle}</p> : null}
        </div>
        <ConfidenceBadge value={clause.confidence} />
      </div>

      <p className="mt-3 text-sm leading-7 text-slate-300">{clause.summary}</p>

      {fields.length > 0 ? (
        <div className="mt-3 rounded-2xl border border-cyan-400/16 bg-cyan-400/6 px-4 py-3 text-sm text-cyan-50/90">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-200/60">结构化字段</div>
            {editMode ? <div className="text-xs text-cyan-100/70">编辑后保存会自动重新审查</div> : null}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {fields.map(([key, value]) => (
              <span key={key} className="rounded-full border border-white/10 bg-slate-950/25 px-3 py-1 text-xs text-slate-200">
                {fieldLabels[key] ?? key}：{typeof value === "object" ? "查看 JSON" : String(value)}
              </span>
            ))}
          </div>

          <details className="mt-3 rounded-2xl border border-white/8 bg-slate-950/25 px-3 py-3">
            <summary className="cursor-pointer text-sm text-white">查看原始 JSON</summary>
            <pre className="thin-scrollbar mt-3 max-h-72 overflow-auto text-xs leading-6 text-slate-200">
              {JSON.stringify(clause.structuredFields ?? {}, null, 2)}
            </pre>
          </details>

          {editMode ? (
            <div className="mt-3 grid gap-3">
              {fields.map(([key, value]) => {
                const currentValue = draftInputs[key] ?? toDisplayValue(value);
                const multiline = typeof value === "object";
                return (
                  <label key={key} className="grid gap-2">
                    <span className="text-xs text-cyan-100/80">{fieldLabels[key] ?? key}</span>
                    {multiline ? (
                      <textarea
                        rows={4}
                        value={currentValue}
                        onChange={(event) => {
                          const nextValue = event.target.value;
                          setDraftInputs((state) => ({ ...state, [key]: nextValue }));
                        }}
                        onBlur={() => {
                          const raw = draftInputs[key] ?? toDisplayValue(value);
                          try {
                            onStructuredFieldChange({ clauseId: clause.id, fieldKey: key, value: JSON.parse(raw) });
                          } catch {
                            onStructuredFieldChange({ clauseId: clause.id, fieldKey: key, value: raw });
                          }
                        }}
                        className="min-h-24 rounded-2xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/24"
                      />
                    ) : (
                      <input
                        value={currentValue}
                        onChange={(event) => {
                          const nextValue = event.target.value;
                          setDraftInputs((state) => ({ ...state, [key]: nextValue }));
                        }}
                        onBlur={() =>
                          onStructuredFieldChange({
                            clauseId: clause.id,
                            fieldKey: key,
                            value: draftInputs[key] ?? toDisplayValue(value),
                          })
                        }
                        className="rounded-2xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/24"
                      />
                    )}
                  </label>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      {clause.references && clause.references.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {clause.references.map((reference) => (
            <span key={reference} className="rounded-full border border-cyan-400/16 bg-cyan-400/6 px-3 py-1 text-xs text-cyan-100">
              引用 {reference}
            </span>
          ))}
        </div>
      ) : null}

      {clause.discoveryReason ? (
        <div className="mt-3 rounded-2xl border border-cyan-400/16 bg-cyan-400/6 px-4 py-3 text-sm leading-7 text-cyan-50/90">
          {clause.discoveryReason}
        </div>
      ) : null}

      <blockquote className="mt-3 rounded-2xl border border-white/8 bg-slate-950/30 px-4 py-3 text-sm leading-7 text-slate-300">
        {clause.rawText}
      </blockquote>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-400">
        <span>页码 {clause.page}</span>
        <span>·</span>
        <span>{clause.needHumanReview ? "建议人工复核" : "自动识别稳定"}</span>
        <span>·</span>
        <span>关联关注点 {clause.relatedAuditFocusIds.length}</span>
      </div>

      <div className="mt-4">
        <EvidenceButton onClick={() => onSelect(clause)} />
      </div>
    </article>
  );
}
