import { Download, FileUp, RefreshCcw, Settings2, Sparkles } from "lucide-react";
import type { ApiHealth, RuntimeModelProbe } from "../../types/base";
import type { ContractTask } from "../../types/contract";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";

interface HeaderBarProps {
  task: ContractTask | null;
  health: ApiHealth | null;
  busy: boolean;
  contractNumber: string | null;
  onOpenAuditConfig: () => void;
  onOpenKnowledgeReview: () => void;
  onUpload: (file: File) => void;
  onLoadSample: () => void;
  onReanalyze: () => void;
  onExport: () => void;
}

const statusMap: Record<string, string> = {
  pending_upload: "待上传",
  processing: "解析中",
  completed: "已完成",
  needs_review: "需复核",
};

function formatProbe(probe: RuntimeModelProbe | undefined, fallback: string) {
  if (!probe) {
    return { label: fallback || "未配置", verified: false, provider: null as string | null };
  }
  return {
    label: probe.resolved_model || probe.configured_model || fallback || "未配置",
    verified: probe.probe_status === "ok",
    provider: probe.provider_host ?? null,
  };
}

function MetaChip({
  tone = "default",
  children,
}: {
  tone?: "default" | "accent";
  children: React.ReactNode;
}) {
  const className =
    tone === "accent"
      ? "border-cyan-400/24 bg-cyan-400/10 text-cyan-100"
      : "border-white/10 bg-white/5 text-slate-300";
  return <span className={`rounded-full border px-3 py-1 text-xs ${className}`}>{children}</span>;
}

function renderModelChip(prefix: string, probe: ReturnType<typeof formatProbe>, healthLoading: boolean) {
  if (healthLoading) {
    return <MetaChip>{prefix} 检测中</MetaChip>;
  }

  const suffix = probe.provider ? ` @ ${probe.provider}` : "";
  return (
    <MetaChip>
      {prefix} {probe.label}
      {suffix}
      {probe.verified ? "" : " · 待校验"}
    </MetaChip>
  );
}

export function HeaderBar({
  task,
  health,
  busy,
  contractNumber,
  onOpenAuditConfig,
  onOpenKnowledgeReview,
  onUpload,
  onLoadSample,
  onReanalyze,
  onExport,
}: HeaderBarProps) {
  const healthLoading = !health;
  const textProbe = formatProbe(health?.runtime_models?.text, health?.text_model ?? task?.modelName ?? "");
  const reviewProbe = formatProbe(health?.runtime_models?.review_llm, health?.llm_model ?? "");
  const visionProbe = formatProbe(health?.runtime_models?.vision, health?.vision_model ?? "");
  const showKnowledgeReview = task?.currentStage === "knowledge_base_review" && !!task.knowledgeBaseReview;
  const knowledgeCompleted = task?.knowledgeBaseReview?.status === "completed";
  const progressPercent = showKnowledgeReview
    ? task?.knowledgeBaseReview?.progressPercent ?? task?.progressPercent ?? 0
    : task?.progressPercent ?? 0;
  const progressLabel = showKnowledgeReview
    ? task?.knowledgeBaseReview?.currentStepLabel ?? "制度校验中"
    : task?.currentStage ?? "processing";
  const statusLabel = showKnowledgeReview
    ? "制度校验中"
    : knowledgeCompleted
      ? "制度校验完成"
      : task
        ? statusMap[task.status] ?? task.status
        : "待上传";
  const showProgressBar = Boolean(task && (busy || showKnowledgeReview));
  const knowledgeButtonLabel = knowledgeCompleted ? "查看制度校验结果" : "查看制度校验进度";

  return (
    <header className="glass-panel rounded-[28px] border border-white/8 px-5 py-4 md:px-6">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
        <div className="min-w-0">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl border border-cyan-400/25 bg-cyan-400/10 p-3 text-cyan-100">
              <Sparkles className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-cyan-200/70">Audit Intelligence Workbench</p>
                  <h1 className="mt-1 font-display text-[28px] leading-tight text-white md:text-[34px]">合同智能解析与审计关注点 Agent</h1>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <MetaChip>任务状态 {statusLabel}</MetaChip>
                  {task ? (
                    <ConfidenceBadge value={task.confidenceOverview.overall ?? 0} label="总览" />
                  ) : (
                    <MetaChip>总览 待生成</MetaChip>
                  )}
                  {showKnowledgeReview ? <MetaChip tone="accent">制度校验 {task?.knowledgeBaseReview?.progressPercent ?? 0}%</MetaChip> : null}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <MetaChip>合同编号 {contractNumber ?? "未提取"}</MetaChip>
                {task?.fileName ? <MetaChip>文件 {task.fileName}</MetaChip> : null}
                <MetaChip tone="accent">已接入制度审查底座</MetaChip>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                {renderModelChip("解析模型", textProbe, healthLoading)}
                {renderModelChip("审查模型", reviewProbe, healthLoading)}
                {renderModelChip("多模态", visionProbe, healthLoading)}
              </div>

              {task?.stageDetail ? <p className="mt-3 text-sm text-cyan-100/80">{task.stageDetail}</p> : null}

              {task?.knowledgeBaseReview ? (
                <button
                  type="button"
                  onClick={onOpenKnowledgeReview}
                  className="mt-3 inline-flex items-center rounded-full border border-cyan-400/24 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-50 transition hover:bg-cyan-400/16"
                >
                  {knowledgeButtonLabel}
                </button>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex w-full flex-col gap-3 xl:w-[520px] xl:items-end">
          {showProgressBar ? (
            <div className="w-full rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 xl:max-w-[380px]">
              <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
                <span>{progressLabel}</span>
                <span>{progressPercent}%</span>
              </div>
              <div className="h-2 rounded-full bg-white/8">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-cyan-400 to-sky-300 transition-all duration-500"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>
          ) : null}

          <div className="flex w-full flex-wrap justify-start gap-2 xl:justify-end">
            <button
              type="button"
              onClick={onOpenAuditConfig}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-sm text-slate-200 transition hover:border-cyan-400/24 hover:bg-white/[0.08]"
            >
              <Settings2 className="h-4 w-4" />
              审计配置
            </button>
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/12 px-4 py-2 text-sm font-medium text-cyan-50 transition hover:bg-cyan-400/18">
              <FileUp className="h-4 w-4" />
              上传合同
              <input
                id="contract-upload-input"
                type="file"
                className="hidden"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onUpload(file);
                  event.currentTarget.value = "";
                }}
              />
            </label>
            <button
              id="load-example-button"
              type="button"
              onClick={onLoadSample}
              className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:border-cyan-400/24 hover:bg-white/8"
            >
              快速载入
            </button>
            <button
              type="button"
              disabled={!task || busy}
              onClick={onReanalyze}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition enabled:hover:border-cyan-400/24 enabled:hover:bg-white/8 disabled:opacity-50"
            >
              <RefreshCcw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
              重新解析
            </button>
            <button
              type="button"
              disabled={!task}
              onClick={onExport}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition enabled:hover:border-cyan-400/24 enabled:hover:bg-white/8 disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              导出结果
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
