import { Plus, RefreshCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { RelationConfig } from "../../types/relation";
import { RelationConfigEditor } from "./RelationConfigEditor";

const typeLabelMap: Record<RelationConfig["configType"], string> = {
  relation_focus: "关系关注",
  rule_check: "规则校验",
  external_check: "外部核验",
};

export function RelationConfigPanel({
  relations,
  activeId,
  onSave,
  onDelete,
  onRegenerateAudit,
  allowRegenerate = true,
}: {
  relations: RelationConfig[];
  activeId: string | null;
  onSave: (value: RelationConfig) => void;
  onDelete: (relationId: string) => void;
  onRegenerateAudit: () => void;
  allowRegenerate?: boolean;
}) {
  const [editing, setEditing] = useState<RelationConfig | null>(null);
  const [creating, setCreating] = useState(false);

  const groups = useMemo(
    () => [
      {
        key: "relation_focus",
        title: "关系关注",
        description: "用户主动定义的关系型关注主题，会影响条款理解与审查关注点生成。",
      },
      {
        key: "rule_check",
        title: "规则校验",
        description: "用于规则引擎的结构化校验配置，支持抽取字段和规则载荷。",
      },
      {
        key: "external_check",
        title: "外部核验",
        description: "提示需要接入企业关系库、主数据或外部系统确认的事项。",
      },
    ].map((group) => ({
      ...group,
      items: relations.filter((item) => item.configType === group.key),
    })),
    [relations],
  );

  return (
    <div className="space-y-4">
      <div className="rounded-[22px] border border-white/8 bg-white/[0.03] p-4">
        <h3 className="text-base font-semibold text-white">审查配置</h3>
        <p className="mt-2 text-sm leading-7 text-slate-300">
          配置先于合同解析存在。你可以先定义关系关注、规则校验和外部核验策略，再用同一套配置去分析不同合同。
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            aria-label="新增审查配置"
            onClick={() => {
              setCreating(true);
              setEditing(null);
            }}
            className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100"
          >
            <Plus className="h-4 w-4" />
            新增审查配置
          </button>
          {allowRegenerate ? (
            <button
              type="button"
              aria-label="按当前配置重新生成审查关注点"
              onClick={onRegenerateAudit}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-200"
            >
              <RefreshCcw className="h-4 w-4" />
              按当前配置重新生成关注点
            </button>
          ) : null}
        </div>
      </div>

      {creating ? (
        <RelationConfigEditor
          onSubmit={(value) => {
            onSave(value);
            setCreating(false);
          }}
          onCancel={() => setCreating(false)}
        />
      ) : null}

      {editing ? (
        <RelationConfigEditor
          initialValue={editing}
          onSubmit={(value) => {
            onSave(value);
            setEditing(null);
          }}
          onCancel={() => setEditing(null)}
        />
      ) : null}

      {groups.map((group) => (
        <section key={group.key} className="space-y-3">
          <div className="rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/60">{group.title}</div>
            <div className="mt-2 text-sm text-slate-300">{group.description}</div>
          </div>
          <div className="space-y-3">
            {group.items.length === 0 ? (
              <div className="rounded-[22px] border border-dashed border-white/10 bg-white/[0.02] px-4 py-6 text-sm text-slate-400">
                暂无 {group.title} 配置。
              </div>
            ) : null}
            {group.items.map((relation) => (
              <article
                key={relation.id}
                id={`card-${relation.id}`}
                className={`rounded-[22px] border p-4 ${
                  activeId === relation.id ? "border-cyan-300/40 bg-cyan-400/[0.08]" : "border-white/8 bg-white/[0.03]"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.2em] text-cyan-200/60">{typeLabelMap[relation.configType]}</p>
                    <h3 className="mt-1 text-base font-semibold text-white">{relation.name}</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full border px-3 py-1 text-[11px] tracking-[0.18em] uppercase ${
                        relation.enabled
                          ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-100"
                          : "border-white/10 bg-white/[0.04] text-slate-400"
                      }`}
                    >
                      {relation.enabled ? "启用" : "停用"}
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-300">
                      {relation.priority}
                    </span>
                  </div>
                </div>

                <p className="mt-3 text-sm leading-7 text-slate-300">{relation.description}</p>
                <div className="mt-4 rounded-2xl border border-white/8 bg-slate-950/25 p-4 text-sm text-slate-300">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">风险提示词</div>
                  <div className="mt-2 leading-7">{relation.riskPrompt}</div>
                </div>

                {relation.rulePayload ? (
                  <pre className="mt-4 overflow-x-auto rounded-2xl border border-white/8 bg-slate-950/35 p-4 text-xs leading-6 text-slate-300">
                    {JSON.stringify(relation.rulePayload, null, 2)}
                  </pre>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-2">
                  {relation.toolSource.map((source) => (
                    <span
                      key={source}
                      className="rounded-full border border-cyan-400/18 bg-cyan-400/8 px-3 py-1 text-xs text-cyan-100"
                    >
                      {source}
                    </span>
                  ))}
                </div>

                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    aria-label={`编辑配置 ${relation.name}`}
                    onClick={() => {
                      setEditing(relation);
                      setCreating(false);
                    }}
                    className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-200"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    aria-label={`删除配置 ${relation.name}`}
                    onClick={() => onDelete(relation.id)}
                    className="inline-flex items-center gap-2 rounded-full border border-rose-400/24 bg-rose-400/10 px-4 py-2 text-sm text-rose-100"
                  >
                    <Trash2 className="h-4 w-4" />
                    删除
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
