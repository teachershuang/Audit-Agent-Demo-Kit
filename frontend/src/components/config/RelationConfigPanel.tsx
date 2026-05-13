import { Plus, RefreshCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import type { RelationConfig } from "../../types/relation";
import { RelationConfigEditor } from "./RelationConfigEditor";

export function RelationConfigPanel({
  relations,
  activeId,
  onSave,
  onDelete,
  onRegenerateAudit,
}: {
  relations: RelationConfig[];
  activeId: string | null;
  onSave: (value: RelationConfig) => void;
  onDelete: (relationId: string) => void;
  onRegenerateAudit: () => void;
}) {
  const [editing, setEditing] = useState<RelationConfig | null>(null);
  const [creating, setCreating] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setCreating(true);
            setEditing(null);
          }}
          className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100"
        >
          <Plus className="h-4 w-4" />
          新增关系类型
        </button>
        <button
          type="button"
          onClick={onRegenerateAudit}
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-slate-200"
        >
          <RefreshCcw className="h-4 w-4" />
          重新生成关注点
        </button>
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

      <div className="space-y-3">
        {relations.map((relation) => (
          <article
            key={relation.id}
            id={`card-${relation.id}`}
            className={`rounded-[22px] border p-4 ${
              activeId === relation.id
                ? "border-cyan-300/40 bg-cyan-400/[0.08]"
                : "border-white/8 bg-white/[0.03]"
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-[0.2em] text-cyan-200/60">Relationship Config</p>
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
            <div className="mt-4 flex flex-wrap gap-2">
              {relation.toolSource.map((source) => (
                <span key={source} className="rounded-full border border-cyan-400/18 bg-cyan-400/8 px-3 py-1 text-xs text-cyan-100">
                  {source}
                </span>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button
                type="button"
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
    </div>
  );
}
