import { Clock3, Cpu, ShieldCheck, TriangleAlert, WandSparkles } from "lucide-react";
import type { AgentStep } from "../../types/audit";

const toneMap = {
  pending: "border-white/10 bg-white/[0.03]",
  running: "border-cyan-400/30 bg-cyan-400/10",
  success: "border-emerald-400/20 bg-emerald-400/10",
  warning: "border-amber-400/20 bg-amber-400/10",
};

const toolMap: Record<string, string> = {
  upload_handler: "上传任务处理",
  document_service: "文档类型识别",
  "document_service + ocr_service": "文档解析与 OCR",
  qwen_service: "Qwen 模型解析",
  evidence_service: "证据定位引擎",
  audit_focus_agent: "关注事项生成器",
  verification_agent: "校验引擎",
};

function summarizeStep(step: AgentStep) {
  if (step.name.includes("章节")) return "系统正在把合同重新整理成可阅读的章节结构。";
  if (step.name.includes("条款")) return "系统正在识别付款、验收、违约等关键条款。";
  if (step.name.includes("关键信息")) return "系统正在抽取主体、金额、期限等核心信息。";
  if (step.name.includes("证据")) return "系统正在把模型结果回链到原文位置。";
  if (step.name.includes("审计关注")) return "系统正在基于文本内容生成需重点关注的风险方向。";
  if (step.name.includes("校验")) return "系统正在交叉检查结果是否完整、是否需要进一步核验。";
  if (step.name.includes("文档")) return "系统正在判断文件类型并准备文本抽取链路。";
  return step.outputSummary;
}

export function AgentTimeline({ steps }: { steps: AgentStep[] }) {
  return (
    <div className="space-y-4">
      <section className="rounded-[22px] border border-cyan-400/18 bg-cyan-400/[0.07] p-4">
        <div className="flex items-center gap-3">
          <div className="rounded-2xl border border-cyan-300/25 bg-cyan-400/10 p-2.5 text-cyan-100">
            <WandSparkles className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">系统处理过程</h3>
            <p className="mt-1 text-sm text-slate-300">
              这里展示的不是底层技术细节，而是系统在当前合同上做了哪些关键动作。
            </p>
          </div>
        </div>
      </section>

      {steps.map((step, index) => (
        <article key={step.id} className={`rounded-[22px] border p-4 ${toneMap[step.status]}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-slate-950/35 text-xs text-slate-200">
                {String(index + 1).padStart(2, "0")}
              </div>
              <div>
                <h3 className="text-base font-semibold text-white">{step.name}</h3>
                <p className="mt-2 text-sm leading-7 text-slate-300">{summarizeStep(step)}</p>
              </div>
            </div>
            <div className="text-right text-xs text-slate-300">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/25 px-3 py-1.5">
                <Clock3 className="h-3.5 w-3.5" />
                {step.durationMs} ms
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300 md:grid-cols-2">
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <Cpu className="h-3.5 w-3.5" />
                系统收到的信息
              </div>
              <div className="mt-2 leading-7">{step.inputSummary}</div>
            </div>
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <ShieldCheck className="h-3.5 w-3.5" />
                当前使用能力
              </div>
              <div className="mt-2 leading-7">{toolMap[step.tool] ?? step.tool}</div>
            </div>
          </div>

          <div className="mt-3 rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-sm leading-7 text-slate-300">
            产出结果：{step.outputSummary}
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
