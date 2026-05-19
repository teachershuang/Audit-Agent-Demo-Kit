export type RelationToolSource =
  | "model_inference"
  | "rule_engine_future"
  | "knowledge_graph_future"
  | "enterprise_relation_future"
  | "internal_master_data_future"
  | "rpa_api_future";

export type AuditConfigType = "relation_focus" | "rule_check" | "external_check";

export interface RelationConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  riskPrompt: string;
  toolSource: RelationToolSource[];
  priority: "low" | "medium" | "high";
  configType: AuditConfigType;
  rulePayload?: Record<string, unknown> | null;
}
