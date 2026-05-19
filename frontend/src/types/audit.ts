export type RiskLevel = "low" | "medium" | "high" | "pending_verification";
export type VerificationStatus = "pass" | "warning" | "fail" | "external_pending";
export type AuditFocusSource =
  | "user_rule_check"
  | "user_relation_check"
  | "user_external_check"
  | "agent_discovered";

export interface AuditFocus {
  id: string;
  title: string;
  focusSource: AuditFocusSource;
  matchedRelationIds: string[];
  riskLevel: RiskLevel;
  reason: string;
  evidenceClauseIds: string[];
  locationText: string;
  confidence: number;
  dependsOn: string[];
  currentBasis: string;
  futureTools: string[];
  modelOnly: boolean;
  humanReviewSuggestion: string;
}

export interface VerificationItem {
  id: string;
  name: string;
  method: string;
  status: VerificationStatus;
  description: string;
  relatedClauseIds: string[];
  relatedEvidenceIds: string[];
  needExternalTool: boolean;
  source?: string;
  configId?: string | null;
  ruleId?: string | null;
  engineStatus?: string | null;
  detail?: Record<string, unknown>;
}

export interface AgentStep {
  id: string;
  name: string;
  status: "pending" | "running" | "success" | "warning";
  durationMs: number;
  inputSummary: string;
  outputSummary: string;
  tool: string;
  success: boolean;
  errorMessage?: string;
}
