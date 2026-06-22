import type { BaseRuleRecord } from "../types/base";

interface RuleManageProps {
  rules: BaseRuleRecord[];
  activeRuleId: string | null;
  metadataLoading: boolean;
  onSelect: (ruleId: string) => Promise<void>;
  onToggle: (rule: BaseRuleRecord) => Promise<void>;
  onRefresh: () => Promise<void>;
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

export function RuleManage({ rules, activeRuleId, metadataLoading, onSelect, onToggle, onRefresh }: RuleManageProps) {
  const enabledCount = rules.filter((item) => item.enabled).length;
  const disabledCount = rules.length - enabledCount;
  const sourceDocumentCount = new Set(rules.map((item) => item.source_document_id).filter(Boolean)).size;
  const deduped = Array.from(new Map(rules.map((item) => [`${item.id}:${item.source_document_id ?? ""}`, item])).values());
  const sorted = [...deduped].sort((left, right) => {
    if (left.enabled !== right.enabled) {
      return left.enabled ? -1 : 1;
    }
    return left.id.localeCompare(right.id, "en");
  });

  return (
    <div className="glass-panel rounded-[28px] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] text-cyan-200/70">Rule Drafts</div>
          <h3 className="mt-2 text-xl font-semibold text-white">规则管理</h3>
        </div>
        <button
          type="button"
          aria-label="刷新规则列表"
          className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"
          onClick={() => void onRefresh()}
        >
          刷新
        </button>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <SummaryCard label="规则总数" value={sorted.length} />
        <SummaryCard label="已启用" value={enabledCount} />
        <SummaryCard label="未启用" value={disabledCount} />
        <SummaryCard label="制度来源文档" value={sourceDocumentCount} />
      </div>

      <div className="mt-5 grid gap-4">
        {sorted.map((rule) => {
          const active = activeRuleId === rule.id;
          return (
            <div
              key={`${rule.id}:${rule.source_document_id ?? ""}`}
              role="button"
              tabIndex={0}
              aria-label={`查看规则 ${rule.name}`}
              onClick={() => void onSelect(rule.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void onSelect(rule.id);
                }
              }}
              className={`rounded-[24px] border p-4 text-left transition ${
                active ? "border-cyan-300/35 bg-cyan-400/[0.08]" : "border-white/10 bg-slate-950/25 hover:border-cyan-400/24"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-medium text-white">{rule.name}</div>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-[11px] ${
                        rule.enabled
                          ? "border-emerald-300/25 bg-emerald-400/10 text-emerald-100"
                          : "border-amber-300/25 bg-amber-400/10 text-amber-100"
                      }`}
                    >
                      {rule.enabled ? "已启用" : "未启用"}
                    </span>
                    {active && metadataLoading ? (
                      <span className="rounded-full border border-cyan-400/24 bg-cyan-400/10 px-2.5 py-1 text-[11px] text-cyan-100">
                        加载中
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-2 text-sm text-slate-300">
                    {rule.id} / {rule.department} / {rule.severity}
                  </div>
                  <div className="mt-2 text-sm text-slate-200">{rule.suggestion_template}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                    <span>依据条款 {rule.basis_policy.length}</span>
                    {rule.source_document_id ? <span>来源文档 {rule.source_document_id}</span> : null}
                    <span>规则阶段 {rule.status === "draft" ? "草案" : rule.status}</span>
                  </div>
                </div>
                <button
                  type="button"
                  aria-label={`${rule.enabled ? "停用" : "启用"}规则 ${rule.name}`}
                  className={`rounded-full px-4 py-2 text-sm ${
                    rule.enabled
                      ? "border border-emerald-300/25 bg-emerald-400/10 text-emerald-100"
                      : "border border-amber-300/25 bg-amber-400/10 text-amber-100"
                  }`}
                  onClick={(event) => {
                    event.stopPropagation();
                    void onToggle(rule);
                  }}
                >
                  {rule.enabled ? "停用" : "启用"}
                </button>
              </div>
            </div>
          );
        })}

        {rules.length === 0 ? <div className="text-sm text-slate-300">暂无规则。</div> : null}
      </div>
    </div>
  );
}
