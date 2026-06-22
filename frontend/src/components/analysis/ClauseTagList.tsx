import type { ClauseTag } from "../../types/contract";
import { ClauseCard } from "./ClauseCard";

export function ClauseTagList({
  clauses,
  activeId,
  editMode,
  hasUnsavedDraft,
  onSelect,
  onToggleEditMode,
  onUndoDraft,
  onDiscardDraft,
  onSaveDraft,
  onStructuredFieldChange,
}: {
  clauses: ClauseTag[];
  activeId: string | null;
  editMode: boolean;
  hasUnsavedDraft: boolean;
  onSelect: (clause: ClauseTag) => void;
  onToggleEditMode: (enabled: boolean) => void;
  onUndoDraft: () => void;
  onDiscardDraft: () => void;
  onSaveDraft: () => void;
  onStructuredFieldChange: (patch: { clauseId: string; fieldKey: string; value: unknown }) => void;
}) {
  const groups = [
    {
      key: "core",
      title: "核心标签",
      description: "标准合同视角下的稳定条款，适合快速浏览。",
      items: clauses.filter((clause) => clause.labelSource === "core"),
    },
    {
      key: "user_configured",
      title: "人工配置标签",
      description: "来自审查配置或专项关注项的定向识别结果。",
      items: clauses.filter((clause) => clause.labelSource === "user_configured"),
    },
    {
      key: "agent_discovered",
      title: "Agent 新发现",
      description: "模型补充识别出的候选条款，建议结合原文复核。",
      items: clauses.filter((clause) => clause.labelSource === "agent_discovered"),
    },
  ].filter((group) => group.items.length > 0);

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-cyan-400/14 bg-cyan-400/[0.06] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-white">结构化字段草稿</div>
            <div className="mt-1 text-sm text-cyan-100/80">主项目与制度底座共用同一份任务结果。保存后会自动重新审查并同步制度底座。</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onToggleEditMode(!editMode)}
              className="rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-sm text-white"
            >
              {editMode ? "退出编辑" : "编辑结构化字段"}
            </button>
            {editMode ? (
              <>
                <button
                  type="button"
                  onClick={onUndoDraft}
                  className="rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-sm text-slate-200"
                >
                  回退一次
                </button>
                <button
                  type="button"
                  onClick={onDiscardDraft}
                  className="rounded-full border border-white/10 bg-white/[0.05] px-4 py-2 text-sm text-slate-200"
                >
                  放弃修改
                </button>
                <button
                  type="button"
                  onClick={onSaveDraft}
                  disabled={!hasUnsavedDraft}
                  className="rounded-full border border-cyan-300/30 bg-cyan-400/15 px-4 py-2 text-sm text-cyan-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  保存并重审
                </button>
              </>
            ) : null}
          </div>
        </div>
      </section>

      {groups.map((group) => (
        <section key={group.key} className="space-y-3">
          <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">{group.title}</div>
            <div className="mt-2 text-sm text-slate-300">{group.description}</div>
          </div>
          <div className="space-y-3">
            {group.items.map((clause) => (
              <ClauseCard
                key={clause.id}
                clause={clause}
                active={activeId === clause.id}
                editMode={editMode}
                onSelect={onSelect}
                onStructuredFieldChange={onStructuredFieldChange}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
