import { useState } from "react";
import type { AuditFocus } from "../../types/audit";
import { api } from "../../services/api";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";
import { RiskBadge } from "../shared/RiskBadge";

function sourceLabel(source: AuditFocus["focusSource"]) {
  switch (source) {
    case "user_rule_check":
      return "用户配置-规则校验";
    case "user_relation_check":
      return "用户配置-关系校验";
    case "user_external_check":
      return "用户配置-外部校验";
    default:
      return "Agent 发现";
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
    default:
      return null;
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

  const requestLogPath = typeof focus.detail?.requestLogPath === "string" ? focus.detail.requestLogPath : null;
  const responseLogPath = typeof focus.detail?.responseLogPath === "string" ? focus.detail.responseLogPath : null;
  const canOpenLogs = focus.focusSource === "user_rule_check" && Boolean(requestLogPath && responseLogPath);

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

  return (
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
            <p className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/60">审计关注方向</p>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-slate-300">
              {sourceLabel(focus.focusSource)}
            </span>
            {executionStatusLabel(focus) ? (
              <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-cyan-100">
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
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">证据位置</div>
          <div className="mt-2">{focus.locationText}</div>
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
        <div className="mt-3 flex flex-wrap items-center gap-2">
        {focus.matchedRelationIds.length ? (
          <div className="text-xs text-slate-400">关联配置 {focus.matchedRelationIds.length} 项</div>
        ) : null}
        {focus.ruleId ? (
          <div className="text-xs text-slate-400">Rule ID {focus.ruleId}</div>
        ) : null}
        </div>
      </button>

      {canOpenLogs ? (
        <div className="mt-4 rounded-2xl border border-cyan-400/18 bg-cyan-400/[0.04] p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-cyan-50">这条关注点来自规则引擎，可直接查看本次请求与返回原文。</div>
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
  );
}
