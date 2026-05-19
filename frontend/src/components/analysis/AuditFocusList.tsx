import type { AuditFocus } from "../../types/audit";
import { AuditFocusCard } from "./AuditFocusCard";

const focusGroups: Array<{
  key: AuditFocus["focusSource"];
  title: string;
  description: string;
}> = [
  {
    key: "user_rule_check",
    title: "用户配置-规则校验",
    description: "这部分关注点严格对应规则引擎执行结果。每条卡片都应能说明是否命中、是否执行失败，以及是否存在引擎请求日志。",
  },
  {
    key: "user_relation_check",
    title: "用户配置-关系校验",
    description: "这部分关注点来自你配置的关系型核验策略，强调主体、供应商、付款链路等关系线索。",
  },
  {
    key: "user_external_check",
    title: "用户配置-外部校验",
    description: "这部分关注点需要外部数据、主数据、知识图谱或业务系统配合才能进一步确认。",
  },
  {
    key: "agent_discovered",
    title: "Agent发现",
    description: "这部分不是你预设的检查项，而是 Agent 基于合同内容主动识别出的关注方向。",
  },
];

export function AuditFocusList({
  items,
  activeId,
  onSelect,
}: {
  items: AuditFocus[];
  activeId: string | null;
  onSelect: (focus: AuditFocus) => void;
}) {
  const groups = focusGroups
    .map((group) => ({
      ...group,
      items: items.filter((item) => item.focusSource === group.key),
    }))
    .filter((group) => group.items.length > 0);

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
