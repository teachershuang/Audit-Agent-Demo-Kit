import type { VerificationItem } from "../../types/audit";
import type { ClauseTag } from "../../types/contract";

const statusMap = {
  pass: "已通过",
  warning: "建议复核",
  fail: "需要补齐",
  external_pending: "待外部核验",
};

const statusTone = {
  pass: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
  warning: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  fail: "border-rose-400/30 bg-rose-400/10 text-rose-100",
  external_pending: "border-cyan-400/30 bg-cyan-400/10 text-cyan-100",
};

function buildUserSummary(item: VerificationItem) {
  switch (item.status) {
    case "pass":
      return "系统已找到足够依据，这一项当前可以继续向下查看。";
    case "warning":
      return "系统识别到了线索，但完整性或一致性还不够稳，建议人工复核。";
    case "fail":
      return "当前没有找到足够支撑内容，建议补充合同条款或重新核验。";
    case "external_pending":
      return "仅靠合同文本无法确认，需要接入外部数据或业务系统继续判断。";
    default:
      return item.description;
  }
}

function humanizeMethod(method: string) {
  return method
    .replaceAll("+", " / ")
    .replaceAll("条款标签识别", "条款识别")
    .replaceAll("原文证据定位", "原文定位")
    .replaceAll("关键词命中", "关键词比对");
}

export function VerificationPanel({
  items,
  clauses,
}: {
  items: VerificationItem[];
  clauses: ClauseTag[];
}) {
  const clauseMap = new Map(clauses.map((item) => [item.id, item]));

  const passedCount = items.filter((item) => item.status === "pass").length;
  const warningCount = items.filter((item) => item.status === "warning").length;
  const pendingCount = items.filter((item) => item.status === "external_pending").length;

  return (
    <div className="space-y-4">
      <section className="grid gap-3 md:grid-cols-3">
        <div className="rounded-[22px] border border-emerald-400/18 bg-emerald-400/8 p-4">
          <div className="text-[11px] uppercase tracking-[0.22em] text-emerald-200/70">已通过</div>
          <div className="mt-2 text-2xl font-semibold text-white">{passedCount}</div>
          <div className="mt-1 text-sm text-slate-300">文本证据和判断逻辑基本一致</div>
        </div>
        <div className="rounded-[22px] border border-amber-400/18 bg-amber-400/8 p-4">
          <div className="text-[11px] uppercase tracking-[0.22em] text-amber-100/70">建议复核</div>
          <div className="mt-2 text-2xl font-semibold text-white">{warningCount}</div>
          <div className="mt-1 text-sm text-slate-300">有识别结果，但还不适合直接采用</div>
        </div>
        <div className="rounded-[22px] border border-cyan-400/18 bg-cyan-400/8 p-4">
          <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-100/70">待外部核验</div>
          <div className="mt-2 text-2xl font-semibold text-white">{pendingCount}</div>
          <div className="mt-1 text-sm text-slate-300">需要企业关系、付款或审批等外部信息</div>
        </div>
      </section>

      <div className="space-y-3">
        {items.map((item) => {
          const relatedLabels = item.relatedClauseIds
            .map((id) => clauseMap.get(id))
            .filter(Boolean)
            .map((clause) => `${clause?.label} · ${clause?.title}`);

          return (
            <article
              key={item.id}
              id={`card-${item.id}`}
              className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.2em] text-cyan-200/60">校验结论</p>
                  <h3 className="mt-1 text-base font-semibold text-white">{item.name}</h3>
                  <p className="mt-2 text-sm leading-7 text-slate-300">{buildUserSummary(item)}</p>
                </div>
                <span
                  className={`rounded-full border px-3 py-1 text-[11px] tracking-[0.12em] ${statusTone[item.status]}`}
                >
                  {statusMap[item.status]}
                </span>
              </div>

              <div className="mt-4 grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300 md:grid-cols-2">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">系统怎么判断</div>
                  <div className="mt-2 leading-7">{humanizeMethod(item.method)}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">关联内容</div>
                  <div className="mt-2 leading-7">
                    {relatedLabels.length > 0 ? relatedLabels.join(" / ") : "当前没有直接关联到具体条款"}
                  </div>
                </div>
              </div>

              <div className="mt-3 rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-sm leading-7 text-slate-300">
                {item.description}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
