import { Download, FileUp, RefreshCcw, Sparkles } from "lucide-react";
import type { ContractTask } from "../../types/contract";
import { ConfidenceBadge } from "../shared/ConfidenceBadge";

interface HeaderBarProps {
  task: ContractTask | null;
  busy: boolean;
  onUpload: (file: File) => void;
  onLoadSample: () => void;
  onReanalyze: () => void;
  onExport: () => void;
}

const statusMap = {
  pending_upload: "待上传",
  processing: "解析中",
  completed: "已完成",
  needs_review: "需复核",
};

export function HeaderBar({
  task,
  busy,
  onUpload,
  onLoadSample,
  onReanalyze,
  onExport,
}: HeaderBarProps) {
  return (
    <header className="glass-panel rounded-[28px] border border-white/8 px-5 py-4 md:px-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl border border-cyan-400/25 bg-cyan-400/10 p-3 text-cyan-100">
            <Sparkles className="h-6 w-6" />
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-cyan-200/70">
              Audit Intelligence Workbench
            </p>
            <h1 className="mt-1 font-display text-2xl text-white md:text-[30px]">
              合同智能解析与审计关注点 Agent
            </h1>
            <p className="mt-2 text-sm text-slate-300">
              合同结构、关键条款、证据定位与审计关注事项统一呈现。
            </p>
            {task?.stageDetail ? (
              <p className="mt-2 text-xs text-cyan-100/80">
                当前阶段：{task.stageDetail}
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex flex-col gap-3 xl:min-w-[420px] xl:items-end">
          <div className="flex w-full flex-col gap-2 xl:items-end">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                任务状态 {task ? statusMap[task.status] : "待上传"}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
                模型 {task?.modelName ?? "Qwen"}
              </span>
              <ConfidenceBadge value={task?.confidenceOverview.overall ?? 0.86} label="总览" />
            </div>
            {busy && task ? (
              <div className="w-full max-w-[340px]">
                <div className="mb-1 flex items-center justify-between text-[11px] text-slate-400">
                  <span>{task.currentStage ?? "processing"}</span>
                  <span>{task.progressPercent}%</span>
                </div>
                <div className="h-2 rounded-full bg-white/8">
                  <div
                    className="h-2 rounded-full bg-gradient-to-r from-cyan-400 to-sky-300 transition-all duration-500"
                    style={{ width: `${task.progressPercent}%` }}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <label className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/12 px-4 py-2 text-sm font-medium text-cyan-50 transition hover:bg-cyan-400/18">
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
