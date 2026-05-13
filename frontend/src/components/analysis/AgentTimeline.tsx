import { Clock3, Cpu, ShieldCheck, TriangleAlert } from "lucide-react";
import type { AgentStep } from "../../types/audit";

const toneMap = {
  pending: "border-white/10 bg-white/[0.03]",
  running: "border-cyan-400/30 bg-cyan-400/10",
  success: "border-emerald-400/20 bg-emerald-400/10",
  warning: "border-amber-400/20 bg-amber-400/10",
};

export function AgentTimeline({ steps }: { steps: AgentStep[] }) {
  return (
    <div className="space-y-3">
      {steps.map((step, index) => (
        <article key={step.id} className={`rounded-[22px] border p-4 ${toneMap[step.status]}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-slate-950/35 text-xs text-slate-200">
                {String(index + 1).padStart(2, "0")}
              </div>
              <div>
                <h3 className="text-base font-semibold text-white">{step.name}</h3>
                <p className="mt-1 text-sm text-slate-300">{step.outputSummary}</p>
              </div>
            </div>
            <div className="text-right text-xs text-slate-300">
              <div className="inline-flex items-center gap-2">
                <Clock3 className="h-3.5 w-3.5" />
                {step.durationMs} ms
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300 md:grid-cols-2">
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <Cpu className="h-3.5 w-3.5" />
                输入
              </div>
              <div className="mt-2">{step.inputSummary}</div>
            </div>
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <ShieldCheck className="h-3.5 w-3.5" />
                工具 / 模型
              </div>
              <div className="mt-2">{step.tool}</div>
            </div>
          </div>

          {step.errorMessage ? (
            <div className="mt-4 inline-flex items-center gap-2 text-sm text-amber-100">
              <TriangleAlert className="h-4 w-4" />
              {step.errorMessage}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}
