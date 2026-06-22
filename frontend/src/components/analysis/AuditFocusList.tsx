import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import type { AuditFocus } from "../../types/audit";
import { AuditFocusCard } from "./AuditFocusCard";

const focusGroups: Array<{
  key: AuditFocus["focusSource"];
  title: string;
  description: string;
}> = [
  {
    key: "knowledge_base_rule_check",
    title: "制度底座 / 规则库校验",
    description: "来自范本比对、制度检索和规则命中。",
  },
  {
    key: "user_rule_check",
    title: "人工配置 / 规则校验",
    description: "来自当前项目规则配置。",
  },
  {
    key: "user_relation_check",
    title: "人工配置 / 关系校验",
    description: "来自主体、付款、履约关系等关系校验。",
  },
  {
    key: "user_external_check",
    title: "人工配置 / 外部核验",
    description: "需要外部系统或主数据配合确认。",
  },
  {
    key: "agent_discovered",
    title: "Agent 主动发现",
    description: "模型主动识别出的风险方向。",
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
  const groups = useMemo(
    () =>
      focusGroups
        .map((group) => ({
          ...group,
          items: items.filter((item) => item.focusSource === group.key),
        }))
        .filter((group) => group.items.length > 0),
    [items],
  );
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(
    Object.fromEntries(groups.map((group, index) => [group.key, index === 0])),
  );

  return (
    <div className="space-y-5">
      {groups.map((group) => {
        const open = openGroups[group.key] ?? false;
        return (
          <section key={group.key} className="space-y-3">
            <button
              type="button"
              onClick={() => setOpenGroups((state) => ({ ...state, [group.key]: !open }))}
              className="flex w-full items-center justify-between rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-left"
            >
              <div>
                <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">{group.title}</div>
                <div className="mt-2 text-sm text-slate-300">{group.description}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-slate-200">
                  {group.items.length} 项
                </span>
                {open ? <ChevronDown className="h-4 w-4 text-slate-300" /> : <ChevronRight className="h-4 w-4 text-slate-300" />}
              </div>
            </button>
            {open ? (
              <div className="space-y-3">
                {group.items.map((item) => (
                  <AuditFocusCard key={item.id} focus={item} active={activeId === item.id} onSelect={onSelect} />
                ))}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
