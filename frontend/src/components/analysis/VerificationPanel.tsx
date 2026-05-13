import type { VerificationItem } from "../../types/audit";

const statusMap = {
  pass: "通过",
  warning: "警告",
  fail: "失败",
  external_pending: "待外部数据",
};

const statusTone = {
  pass: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
  warning: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  fail: "border-rose-400/30 bg-rose-400/10 text-rose-100",
  external_pending: "border-cyan-400/30 bg-cyan-400/10 text-cyan-100",
};

export function VerificationPanel({ items }: { items: VerificationItem[] }) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <article key={item.id} id={`card-${item.id}`} className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.2em] text-cyan-200/60">校验项</p>
              <h3 className="mt-1 text-base font-semibold text-white">{item.name}</h3>
            </div>
            <span className={`rounded-full border px-3 py-1 text-[11px] tracking-[0.18em] uppercase ${statusTone[item.status]}`}>
              {statusMap[item.status]}
            </span>
          </div>
          <p className="mt-3 text-sm leading-7 text-slate-300">{item.description}</p>
          <div className="mt-4 grid gap-3 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300 md:grid-cols-2">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">校验方式</div>
              <div className="mt-2">{item.method}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">关联条款</div>
              <div className="mt-2">{item.relatedClauseIds.join(", ") || "无"}</div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
