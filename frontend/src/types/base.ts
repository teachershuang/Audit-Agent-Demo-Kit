export interface TemplateCatalogItem {
  template_id: string;
  template_name: string;
  category_lv1?: string | null;
  category_lv2?: string | null;
  start_page: number;
  end_page: number;
  preview_page?: number | null;
  clause_count?: number | null;
  signature?: string | null;
  key_clause_titles?: string[];
  auto_variant_cues?: string[];
  auto_variant_summary?: string | null;
  usage_profile?: string | null;
  usage_profile_basis?: string[];
  usage_profile_summary?: string | null;
  same_name_index?: number | null;
  same_name_total?: number | null;
  disambiguation_label?: string | null;
}

export interface BaseDocumentRecord {
  id: string;
  name: string;
  doc_type: string;
  category?: string | null;
  version: string;
  issuer?: string | null;
  status: string;
  effective_date?: string | null;
  effective_ts: number;
  abolish_date?: string | null;
  abolish_ts: number;
  replaced_by?: string | null;
  file_hash: string;
  source_file: string;
  confidential_level: string;
  created_at: string;
  template_count: number;
  source_kind: string;
  current_version_flag: boolean;
  template_catalog: TemplateCatalogItem[];
}

export interface BaseClauseRecord {
  id: string;
  document_id: string;
  doc_type: string;
  template_id?: string | null;
  template_name?: string | null;
  category_lv1?: string | null;
  category_lv2?: string | null;
  clause_no?: string | null;
  title: string;
  clause_type: string;
  content: string;
  page_start: number;
  page_end: number;
  status: string;
  effective_ts: number;
  abolish_ts: number;
  risk_tags: string[];
  preview?: {
    page?: number | null;
    image_url?: string | null;
    excerpt?: string | null;
    boxes?: Array<{
      x0: number;
      y0: number;
      x1: number;
      y1: number;
    }> | null;
    page_width?: number | null;
    page_height?: number | null;
  } | null;
}

export interface BaseRuleRecord {
  id: string;
  name: string;
  enabled: boolean;
  rule_type: string;
  contract_categories: string[];
  severity: string;
  basis_policy: string[];
  logic: Record<string, unknown>;
  suggestion_template: string;
  department: string;
  source_document_id?: string | null;
  status: string;
}

export interface BaseDocumentMetadataSummary {
  clause_count: number;
  effective_clause_count: number;
  rule_count: number;
  enabled_rule_count: number;
  template_count: number;
  source_kind: string;
  current_version_flag: boolean;
}

export interface BaseDocumentVersionContext {
  same_series: BaseDocumentRecord[];
  previous_versions: BaseDocumentRecord[];
  next_version?: BaseDocumentRecord | null;
}

export interface BaseDocumentMetadata {
  document: BaseDocumentRecord;
  summary?: BaseDocumentMetadataSummary;
  version_context?: BaseDocumentVersionContext;
  clauses: BaseClauseRecord[];
  rules: BaseRuleRecord[];
}

export interface BaseClauseMetadata {
  clause: BaseClauseRecord;
  summary?: {
    linked_rule_count: number;
    template_name?: string | null;
    category_path?: string | null;
  };
  document?: BaseDocumentRecord | null;
  source_document_context?: BaseDocumentVersionContext | null;
  linked_rules: BaseRuleRecord[];
}

export interface BaseRuleMetadata {
  rule: BaseRuleRecord;
  summary?: {
    source_clause_count: number;
    enabled: boolean;
    status: string;
    source_document_name?: string | null;
  };
  source_document?: BaseDocumentRecord | null;
  source_document_context?: BaseDocumentVersionContext | null;
  source_clauses: BaseClauseRecord[];
}

export interface SourceTaskSummary {
  task_id: string;
  file_name: string;
  status: string;
  created_at: string;
}

export interface BaseContractSchema {
  contract_id: string;
  source_task_id: string;
  detected_category: string;
  matched_template_id?: string | null;
  matched_template_name?: string | null;
  fields: Record<string, string | null>;
  clauses: Array<Record<string, unknown>>;
  created_at: string;
}

export interface BaseReviewIssue {
  id: string;
  severity: string;
  department: string;
  clause_location: string;
  problem: string;
  basis_policy: string[];
  basis_policy_details?: Array<Record<string, unknown>>;
  basis_template?: string | null;
  basis_template_detail?: Record<string, unknown> | null;
  source_rule_id?: string | null;
  source_rule_name?: string | null;
  suggestion: string;
  confidence: number;
  extra?: Record<string, unknown>;
  preview?: {
    page?: number | null;
    page_title?: string | null;
    clause_title?: string | null;
    fact_label?: string | null;
    evidence_id?: string | null;
    excerpt?: string | null;
    image_url?: string | null;
    note?: string | null;
  } | null;
}

export interface BaseReviewReport {
  contract_id: string;
  source_task_id?: string;
  status: string;
  matched_template?: {
    template_id?: string | null;
    template_name?: string | null;
    category_lv1?: string | null;
    category_lv2?: string | null;
  } | null;
  detected_category: string;
  summary: string;
  issues: BaseReviewIssue[];
  created_at: string;
}

export interface BaseReviewTask {
  task_id: string;
  source_task_id: string;
  selected_template_id?: string | null;
  status: string;
  message: string;
  created_at: string;
  updated_at: string;
  contract_id?: string | null;
  issue_count?: number | null;
  detected_category?: string | null;
  matched_template?: {
    template_id?: string | null;
    template_name?: string | null;
    category_lv1?: string | null;
    category_lv2?: string | null;
  } | null;
  error?: string | null;
}

export interface RuntimeModelProbe {
  capability: string;
  configured_model?: string | null;
  resolved_model?: string | null;
  provider_host?: string | null;
  available: boolean;
  probe_status: string;
  probe_method: string;
  checked_at?: string | null;
  available_models_count?: number;
  error?: string | null;
}

export interface ApiHealth {
  status: string;
  app: string;
  mode: string;
  active_profile_id?: string;
  active_profile_label?: string;
  text_model: string;
  vision_model: string;
  llm_model: string;
  embedding_model: string;
  knowledge_base_enabled: boolean;
  runtime_models?: {
    text?: RuntimeModelProbe;
    vision?: RuntimeModelProbe;
    review_llm?: RuntimeModelProbe;
    embedding?: RuntimeModelProbe;
  };
}

export interface RuntimeModelProfileSummary {
  id: string;
  label: string;
  description: string;
  textModel: string;
  visionModel?: string | null;
  reviewModel: string;
  ocrStrategy: string;
  paddleMode: string;
  paddleRemoteBaseUrl?: string | null;
}

export interface RuntimeModelProfileState {
  currentProfileId: string;
  currentProfileLabel: string;
  profiles: RuntimeModelProfileSummary[];
  runtimeModels: ApiHealth["runtime_models"];
  paddleProbe?: {
    mode: string;
    available: boolean;
    provider?: string | null;
    status: string;
    raw?: Record<string, unknown>;
    error?: string | null;
  };
}
