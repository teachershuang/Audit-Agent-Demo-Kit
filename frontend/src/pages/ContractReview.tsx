import type { SourceTaskSummary } from "../types/base";

interface ContractReviewProps {
  tasks: SourceTaskSummary[];
  busy: boolean;
  onReview: (payload: { sourceTaskId: string; selectedTemplateId: string }) => Promise<void>;
}

export function ContractReview({ tasks, busy, onReview }: ContractReviewProps) {
  return (
    <div className="glass-panel rounded-[28px] p-5">
      <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Contract Review</div>
      <h3 className="mt-2 text-xl font-semibold text-white">合同审查</h3>
      <div className="mt-4 rounded-2xl border border-cyan-400/16 bg-cyan-400/[0.06] px-4 py-3 text-sm text-cyan-50/90">
        复用主项目解析结果。完成后自动跳转到审查报告。
      </div>

      <form
        className="mt-5 grid gap-4 md:grid-cols-[1fr_1fr_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const sourceTaskId = String(form.get("sourceTaskId") || "");
          const selectedTemplateId = String(form.get("selectedTemplateId") || "");
          if (!sourceTaskId) return;
          void onReview({ sourceTaskId, selectedTemplateId });
        }}
      >
        <label className="space-y-2 text-sm text-slate-200">
          <span>待审合同任务</span>
          <select
            name="sourceTaskId"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3"
          >
            <option value="">选择已解析任务</option>
            {tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {task.file_name} / {task.task_id}
              </option>
            ))}
          </select>
        </label>

        <label className="space-y-2 text-sm text-slate-200">
          <span>指定范本 ID</span>
          <input
            name="selectedTemplateId"
            placeholder="可选，不填则自动匹配"
            className="w-full rounded-2xl border border-white/10 bg-slate-950/25 px-4 py-3"
          />
        </label>

        <div className="flex items-end">
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-full border border-cyan-400/30 bg-cyan-400/12 px-5 py-3 text-sm font-medium text-cyan-50 disabled:opacity-50"
          >
            {busy ? "审查中..." : "发起审查"}
          </button>
        </div>
      </form>

      <div className="mt-6 grid gap-3">
        {tasks.map((task) => (
          <div
            key={task.task_id}
            className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-200"
          >
            <div className="font-medium text-white">{task.file_name}</div>
            <div className="mt-1 text-slate-400">
              {task.task_id} / {task.status} / {task.created_at}
            </div>
          </div>
        ))}

        {tasks.length === 0 ? <div className="text-sm text-slate-300">暂无可审查任务。</div> : null}
      </div>
    </div>
  );
}
