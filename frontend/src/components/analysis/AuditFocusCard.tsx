import { useState } from "react";
import { api } from "../../services/api";
import type { AuditFocus } from "../../types/audit";
import { KnowledgeInspectorModal, type KnowledgeSelection } from "../knowledge/KnowledgeInspectorModal";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";
import { RiskBadge } from "../shared/RiskBadge";

function sourceLabel(source: AuditFocus["focusSource"]) {
  switch (source) {
    case "knowledge_base_rule_check":
      return "制度底座 / 规则库";
    case "user_rule_check":
      return "人工配置 / 规则校验";
    case "user_relation_check":
      return "人工配置 / 关系校验";
    case "user_external_check":
      return "人工配置 / 外部核验";
    default:
      return "Agent 主动发现";
  }
}

function executionStatusLabel(focus: AuditFocus) {
  switch (focus.engineStatus) {
    case "hit":
      return "规则命中";
    case "not_hit":
      return "规则未命中";
    case "missing_in_engine":
      return "规则未上传";
    case "engine_error":
      return "引擎执行失败";
    case "not_connected":
      return "引擎未接入";
    case "knowledge_base_hit":
      return "制度底座命中";
    default:
      return null;
  }
}

function executionStatusTone(focus: AuditFocus) {
  switch (focus.engineStatus) {
    case "hit":
    case "knowledge_base_hit":
      return "border-rose-400/25 bg-rose-400/10 text-rose-100";
    case "not_hit":
      return "border-emerald-400/20 bg-emerald-400/10 text-emerald-100";
    case "missing_in_engine":
    case "engine_error":
    case "not_connected":
      return "border-amber-400/20 bg-amber-400/10 text-amber-100";
    default:
      return "border-white/10 bg-white/[0.04] text-slate-300";
  }
}

export function AuditFocusCard({
  focus,
  active,
  onSelect,
}: {
  focus: AuditFocus;
  active: boolean;
  onSelect: (focus: AuditFocus) => void;
}) {
  const [logOpen, setLogOpen] = useState(false);
  const [requestLog, setRequestLog] = useState<string | null>(null);
  const [responseLog, setResponseLog] = useState<string | null>(null);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selection, setSelection] = useState<KnowledgeSelection | null>(null);

  const requestLogPath = typeof focus.detail?.requestLogPath === "string" ? focus.detail.requestLogPath : null;
  const responseLogPath = typeof focus.detail?.responseLogPath === "string" ? focus.detail.responseLogPath : null;
  const basisPolicyDetails = Array.isArray(focus.detail?.basisPolicyDetails)
    ? (focus.detail?.basisPolicyDetails as Array<Record<string, unknown>>)
    : [];
  const basisTemplate = focus.detail?.basisTemplate as Record<string, unknown> | undefined;
  const sourceRuleName = typeof focus.detail?.sourceRuleName === "string" ? focus.detail.sourceRuleName : null;
  const sourceRuleId =
    typeof focus.detail?.sourceRuleId === "string"
      ? focus.detail.sourceRuleId
      : typeof focus.ruleId === "string"
        ? focus.ruleId
        : null;
  const canInspectKnowledgeRule = focus.focusSource === "knowledge_base_rule_check" && Boolean(sourceRuleId);
  const isRuleCheck = focus.focusSource === "user_rule_check";
  const canOpenLogs = isRuleCheck && Boolean(requestLogPath && responseLogPath);

  const loadLogs = async () => {
    if (!canOpenLogs || !requestLogPath || !responseLogPath) return;
    if (requestLog && responseLog) {
      setLogOpen((value) => !value);
      return;
    }
    setLoadingLogs(true);
    setLogError(null);
    try {
      const [requestPayload, responsePayload] = await Promise.all([
        api.getLogFile(requestLogPath),
        api.getLogFile(responseLogPath),
      ]);
      setRequestLog(requestPayload.content);
      setResponseLog(responsePayload.content);
      setLogOpen(true);
    } catch (error) {
      setLogError(error instanceof Error ? error.message : "无法加载规则引擎日志");
    } finally {
      setLoadingLogs(false);
    }
  };

  function openInspector(nextSelection: KnowledgeSelection) {
    setSelection(nextSelection);
    setInspectorOpen(true);
  }

  return (
    <>
      <div
        id={`card-${focus.id}`}
        className={`w-full rounded-[24px] border p-4 text-left transition ${
          active ? "border-cyan-300/40 bg-cyan-400/[0.08]" : "border-white/8 bg-white/[0.03]"
        }`}
      >
        <button type="button" onClick={() => onSelect(focus)} className="w-full text-left">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">审查关注方向</p>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                  {sourceLabel(focus.focusSource)}
                </span>
                {executionStatusLabel(focus) ? (
                  <span
                    className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] ${executionStatusTone(focus)}`}
                  >
                    {executionStatusLabel(focus)}
                  </span>
                ) : null}
              </div>
              <h3 className="mt-1 text-base font-semibold text-white">{focus.title}</h3>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <RiskBadge level={focus.riskLevel} />
              <ConfidenceBadge value={focus.confidence} />
            </div>
          </div>

          <p className="mt-3 text-sm leading-7 text-slate-300">{focus.reason}</p>

          <div className="mt-4 grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300 md:grid-cols-2">
            <div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">定位信息</div>
              <div className="mt-2">{focus.locationText || "未定位到原文"}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">当前判断依据</div>
              <div className="mt-2">{focus.currentBasis}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">依赖数据</div>
              <div className="mt-2">{focus.dependsOn.join(" / ") || "未标注"}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">建议后续工具</div>
              <div className="mt-2">{focus.futureTools.join(" / ") || "无"}</div>
            </div>
          </div>

          <p className="mt-4 text-sm leading-7 text-cyan-100/90">{focus.humanReviewSuggestion}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            {focus.matchedRelationIds.length ? <div>关联配置 {focus.matchedRelationIds.length} 项</div> : null}
            {sourceRuleId ? <div>规则 ID {sourceRuleId}</div> : null}
            {sourceRuleName ? <div>规则名称 {sourceRuleName}</div> : null}
            {focus.configId ? <div>配置 ID {focus.configId}</div> : null}
          </div>
        </button>

        {basisPolicyDetails.length > 0 || basisTemplate || canInspectKnowledgeRule ? (
          <div className="mt-4 rounded-2xl border border-white/8 bg-white/[0.03] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">来源明细</div>
              {canInspectKnowledgeRule ? (
                <button
                  type="button"
                  onClick={() => openInspector({ ruleId: sourceRuleId! })}
                  className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1.5 text-xs text-cyan-100"
                >
                  查看规则依据
                </button>
              ) : null}
            </div>

            {basisPolicyDetails.length > 0 ? (
              <div className="mt-3 space-y-2">
                {basisPolicyDetails.map((item, index) => {
                  const clauseId = typeof item.id === "string" ? item.id : null;
                  const pageStart = item.page_start ? String(item.page_start) : null;
                  const pageEnd = item.page_end ? String(item.page_end) : null;
                  return (
                    <div
                      key={String(item.id ?? index)}
                      className="rounded-2xl border border-cyan-400/14 bg-cyan-400/[0.05] px-3 py-3 text-sm text-slate-200"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-medium text-white">{String(item.title ?? item.id ?? "制度条款")}</div>
                          <div className="mt-1 text-xs text-slate-400">
                            {pageStart ? `第 ${pageStart}${pageEnd ? `-${pageEnd}` : ""} 页` : "制度依据"}
                          </div>
                        </div>
                        {clauseId ? (
                          <button
                            type="button"
                            onClick={() => openInspector({ clauseId })}
                            className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-3 py-1.5 text-xs text-cyan-100"
                          >
                            查看原文
                          </button>
                        ) : null}
                      </div>
                      <div className="mt-2 leading-6 text-slate-300">{String(item.content ?? "")}</div>
                    </div>
                  );
                })}
              </div>
            ) : null}

            {basisTemplate ? (
              <div className="mt-3 rounded-2xl border border-amber-400/14 bg-amber-400/[0.05] px-3 py-3 text-sm text-slate-200">
                <div className="font-medium text-white">{String(basisTemplate.template_name ?? "匹配范本")}</div>
                <div className="mt-1 text-xs text-slate-400">
                  {[basisTemplate.category_lv1, basisTemplate.category_lv2].filter(Boolean).join(" / ")}
                </div>
                {basisTemplate.matched_clause_title ? (
                  <div className="mt-2 text-slate-300">
                    关联条款：{String(basisTemplate.matched_clause_title)}
                    {basisTemplate.matched_clause_page ? ` / 第 ${String(basisTemplate.matched_clause_page)} 页` : ""}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {isRuleCheck ? (
          <div className="mt-4 rounded-2xl border border-cyan-400/18 bg-cyan-400/[0.04] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm text-cyan-50">
                {canOpenLogs ? "这条关注点来自规则引擎，可直接查看本次请求与返回原文。" : "这条关注点属于规则校验，但当前没有可用的引擎请求或返回日志。"}
              </div>
              {canOpenLogs ? (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void loadLogs();
                  }}
                  className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-4 py-2 text-xs text-cyan-100"
                >
                  {loadingLogs ? "加载中..." : logOpen ? "收起引擎日志" : "查看引擎日志"}
                </button>
              ) : null}
            </div>
            {logError ? <div className="mt-3 text-xs text-rose-200">{logError}</div> : null}
            {logOpen && requestLog && responseLog ? (
              <div className="mt-3 grid gap-3 xl:grid-cols-2">
                <div>
                  <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">规则引擎请求原文</div>
                  <pre className="max-h-72 overflow-auto rounded-2xl border border-white/8 bg-slate-950/55 p-3 text-xs leading-6 text-slate-200">
                    {requestLog}
                  </pre>
                </div>
                <div>
                  <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">规则引擎返回原文</div>
                  <pre className="max-h-72 overflow-auto rounded-2xl border border-white/8 bg-slate-950/55 p-3 text-xs leading-6 text-slate-200">
                    {responseLog}
                  </pre>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <KnowledgeInspectorModal open={inspectorOpen} selection={selection} onClose={() => setInspectorOpen(false)} />
    </>
  );
}
