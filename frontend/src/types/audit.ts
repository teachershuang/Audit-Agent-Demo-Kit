export type RiskLevel = "low" | "medium" | "high" | "pending_verification";
export type VerificationStatus = "pass" | "warning" | "fail" | "external_pending";

export interface AuditFocus {
  id: string;
  title: string;
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
