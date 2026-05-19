import { useMemo, useState } from "react";
import type { AuditConfigType, RelationConfig, RelationToolSource } from "../../types/relation";

const sourceOptions: Array<{ value: RelationToolSource; label: string }> = [
  { value: "model_inference", label: "模型推理" },
  { value: "rule_engine_future", label: "规则引擎" },
  { value: "knowledge_graph_future", label: "知识图谱" },
  { value: "enterprise_relation_future", label: "企业关系数据" },
  { value: "internal_master_data_future", label: "内部主数据" },
  { value: "rpa_api_future", label: "RPA / API" },
];

const typeOptions: Array<{ value: AuditConfigType; label: string }> = [
  { value: "relation_focus", label: "关系关注" },
  { value: "rule_check", label: "规则校验" },
  { value: "external_check", label: "外部核验" },
];

function prettyRulePayload(value: Record<string, unknown> | null | undefined) {
  return value ? JSON.stringify(value, null, 2) : "";
}

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
      id: `config_${crypto.randomUUID().slice(0, 8)}`,
      name: "",
      description: "",
      enabled: true,
      riskPrompt: "",
      toolSource: ["model_inference"],
      priority: "medium",
      configType: "relation_focus",
      rulePayload: null,
    },
  );
  const [rulePayloadText, setRulePayloadText] = useState(prettyRulePayload(initialValue?.rulePayload));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const title = useMemo(() => (initialValue ? "编辑审计配置" : "新增审计配置"), [initialValue]);

  return (
    <div className="rounded-[24px] border border-white/8 bg-slate-950/30 p-4">
      <div className="mb-4">
        <h3 className="font-display text-lg text-white">{title}</h3>
        <p className="mt-1 text-sm text-slate-400">配置关注维度、规则输入和后续工具来源。</p>
      </div>

      <div className="grid gap-3">
        <input
          value={value.name}
          onChange={(event) => setValue({ ...value, name: event.target.value })}
          placeholder="配置名称"
          className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/35"
        />
        <textarea
          value={value.description}
          onChange={(event) => setValue({ ...value, description: event.target.value })}
          placeholder="配置说明"
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

        <div className="grid gap-3 md:grid-cols-3">
          <select
            value={value.configType}
            onChange={(event) => setValue({ ...value, configType: event.target.value as AuditConfigType })}
            className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/35"
          >
            {typeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            value={value.priority}
            onChange={(event) => setValue({ ...value, priority: event.target.value as RelationConfig["priority"] })}
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
        </div>

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

        {value.configType === "rule_check" ? (
          <textarea
            value={rulePayloadText}
            onChange={(event) => setRulePayloadText(event.target.value)}
            placeholder='规则载荷 JSON，例如 {"ruleId":"missing_contract_number","extractFields":[{"label":"付款节点","description":"提取付款节点"}]}'
            rows={7}
            className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 font-mono text-xs text-white outline-none focus:border-cyan-400/35"
          />
        ) : null}

        <div className="grid gap-3 md:grid-cols-[1fr_120px]">
          <button
            type="button"
            onClick={() => {
              let nextRulePayload: Record<string, unknown> | null = value.rulePayload ?? null;
              if (value.configType === "rule_check") {
                try {
                  nextRulePayload = rulePayloadText.trim()
                    ? (JSON.parse(rulePayloadText) as Record<string, unknown>)
                    : null;
                  setJsonError(null);
                } catch {
                  setJsonError("规则载荷 JSON 格式不正确。");
                  return;
                }
              }
              onSubmit({ ...value, rulePayload: nextRulePayload });
            }}
            className="rounded-2xl border border-cyan-400/30 bg-cyan-400/12 px-4 py-3 text-sm font-medium text-cyan-50"
          >
            保存
          </button>
          {onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-300"
            >
              取消
            </button>
          ) : null}
        </div>
        {jsonError ? <div className="text-sm text-rose-200">{jsonError}</div> : null}
      </div>
    </div>
  );
}
