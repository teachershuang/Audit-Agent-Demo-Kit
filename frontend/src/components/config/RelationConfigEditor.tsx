import { useMemo, useState } from "react";
import type { RelationConfig, RelationToolSource } from "../../types/relation";

const sourceOptions: Array<{ value: RelationToolSource; label: string }> = [
  { value: "model_inference", label: "模型推理" },
  { value: "rule_engine_future", label: "规则引擎" },
  { value: "knowledge_graph_future", label: "知识图谱" },
  { value: "enterprise_relation_future", label: "企业关系数据" },
  { value: "internal_master_data_future", label: "内部主数据" },
  { value: "rpa_api_future", label: "RPA / API" },
];

export function RelationConfigEditor({
  initialValue,
  onSubmit,
  onCancel,
}: {
  initialValue?: RelationConfig | null;
  onSubmit: (value: RelationConfig) => void;
  onCancel?: () => void;
}) {
  const [value, setValue] = useState<RelationConfig>(
    initialValue ?? {
      id: `relation_${crypto.randomUUID().slice(0, 8)}`,
      name: "",
      description: "",
      enabled: true,
      riskPrompt: "",
      toolSource: ["model_inference"],
      priority: "medium",
    },
  );

  const title = useMemo(() => (initialValue ? "编辑关系条目" : "新增关系条目"), [initialValue]);

  return (
    <div className="rounded-[24px] border border-white/8 bg-slate-950/30 p-4">
      <div className="mb-4">
        <h3 className="font-display text-lg text-white">{title}</h3>
        <p className="mt-1 text-sm text-slate-400">配置分析维度、工具来源与输出优先级。</p>
      </div>

      <div className="grid gap-3">
        <input
          value={value.name}
          onChange={(event) => setValue({ ...value, name: event.target.value })}
          placeholder="关系名称"
          className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/35"
        />
        <textarea
          value={value.description}
          onChange={(event) => setValue({ ...value, description: event.target.value })}
          placeholder="关系说明"
          rows={3}
          className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/35"
        />
        <textarea
          value={value.riskPrompt}
          onChange={(event) => setValue({ ...value, riskPrompt: event.target.value })}
          placeholder="风险提示词"
          rows={4}
          className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/35"
        />

        <div className="flex flex-wrap gap-2">
          {sourceOptions.map((option) => {
            const active = value.toolSource.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                onClick={() =>
                  setValue({
                    ...value,
                    toolSource: active
                      ? value.toolSource.filter((item) => item !== option.value)
                      : [...value.toolSource, option.value],
                  })
                }
                className={`rounded-full border px-3 py-1.5 text-xs transition ${
                  active
                    ? "border-cyan-300/40 bg-cyan-400/10 text-cyan-100"
                    : "border-white/10 bg-white/[0.04] text-slate-300"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        <div className="grid gap-3 md:grid-cols-[1fr_160px_120px]">
          <select
            value={value.priority}
            onChange={(event) =>
              setValue({
                ...value,
                priority: event.target.value as RelationConfig["priority"],
              })
            }
            className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/35"
          >
            <option value="low">低优先级</option>
            <option value="medium">中优先级</option>
            <option value="high">高优先级</option>
          </select>
          <button
            type="button"
            onClick={() => setValue({ ...value, enabled: !value.enabled })}
            className={`rounded-2xl border px-4 py-3 text-sm ${
              value.enabled
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
                : "border-white/10 bg-white/[0.04] text-slate-300"
            }`}
          >
            {value.enabled ? "已启用" : "已停用"}
          </button>
          <button
            type="button"
            onClick={() => onSubmit(value)}
            className="rounded-2xl border border-cyan-400/30 bg-cyan-400/12 px-4 py-3 text-sm font-medium text-cyan-50"
          >
            保存
          </button>
        </div>
        {onCancel ? (
          <button type="button" onClick={onCancel} className="text-left text-sm text-slate-400">
            取消编辑
          </button>
        ) : null}
      </div>
    </div>
  );
}
