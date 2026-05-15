import type { ClauseTag } from "../../types/contract";
import { ClauseCard } from "./ClauseCard";

export function ClauseTagList({
  clauses,
  activeId,
  onSelect,
}: {
  clauses: ClauseTag[];
  activeId: string | null;
  onSelect: (clause: ClauseTag) => void;
}) {
  const groups = [
    {
      key: "core",
      title: "核心标签",
      description: "稳定口径，适合管理层快速浏览。",
      items: clauses.filter((clause) => clause.labelSource === "core"),
    },
    {
      key: "user_configured",
      title: "用户配置标签",
      description: "来自你主动配置的关注内容。",
      items: clauses.filter((clause) => clause.labelSource === "user_configured"),
    },
    {
      key: "agent_discovered",
      title: "Agent 新发现",
      description: "模型额外识别出的候选条款，建议结合原文复核。",
      items: clauses.filter((clause) => clause.labelSource === "agent_discovered"),
    },
  ].filter((group) => group.items.length > 0);

  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <section key={group.key} className="space-y-3">
          <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">{group.title}</div>
            <div className="mt-2 text-sm text-slate-300">{group.description}</div>
          </div>
          <div className="space-y-3">
            {group.items.map((clause) => (
              <ClauseCard key={clause.id} clause={clause} active={activeId === clause.id} onSelect={onSelect} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
