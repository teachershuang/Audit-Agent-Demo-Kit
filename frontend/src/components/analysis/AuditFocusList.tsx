import type { AuditFocus } from "../../types/audit";
import { AuditFocusCard } from "./AuditFocusCard";

export function AuditFocusList({
  items,
  activeId,
  onSelect,
}: {
  items: AuditFocus[];
  activeId: string | null;
  onSelect: (focus: AuditFocus) => void;
}) {
  const groups = [
    {
      key: "relation_config",
      title: "用户关注项触发",
      description: "由关系配置直接触发，便于展示你主动关心的核验方向。",
      items: items.filter((item) => item.focusSource === "relation_config"),
    },
    {
      key: "hybrid",
      title: "配置 + Agent 共同触发",
      description: "既命中了用户配置，也有 Agent 的额外语义判断支撑。",
      items: items.filter((item) => item.focusSource === "hybrid"),
    },
    {
      key: "agent_discovered",
      title: "Agent 主动发现",
      description: "不是用户显式配置，但模型认为值得关注的方向。",
      items: items.filter((item) => item.focusSource === "agent_discovered"),
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
            {group.items.map((item) => (
              <AuditFocusCard key={item.id} focus={item} active={activeId === item.id} onSelect={onSelect} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
