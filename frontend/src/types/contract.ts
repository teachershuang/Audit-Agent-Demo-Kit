export type TaskStatus = "pending_upload" | "processing" | "completed" | "needs_review";
export type AnalysisTab = "sections" | "clauses" | "relations" | "audit" | "verification" | "logs";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EvidenceRef {
  id: string;
  page: number;
  bbox: [number, number, number, number];
  text: string;
  sourceType: "section" | "clause" | "fact";
  sourceId: string;
  segmentIndex: number;
  segmentCount: number;
  isPrimary: boolean;
  accent?: "cyan" | "amber";
}

export interface ContractSection {
  id: string;
  title: string;
  level: number;
  page: number;
  summary: string;
  confidence: number;
  evidenceId?: string;
}

export interface ClauseTag {
  id: string;
  label: string;
  coreLabel: string;
  labelSource: "core" | "agent_discovered" | "user_configured";
  title: string;
  summary: string;
  rawText: string;
  page: number;
  confidence: number;
  evidenceId: string;
  needHumanReview: boolean;
  discoveryReason?: string | null;
  relatedAuditFocusIds: string[];
}

export interface DocumentBlock {
  id: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height?: number;
  emphasis?: boolean;
}

export interface ContractPage {
  page: number;
  title: string;
  width: number;
  height: number;
  imageUrl?: string | null;
  blocks: DocumentBlock[];
  evidences: EvidenceRef[];
}

export interface KeyFact {
  id: string;
  label: string;
  value: string;
  page: number;
  confidence: number;
  evidenceId?: string | null;
  notes?: string | null;
}

export interface ConfidenceOverview {
  overall: number;
  sections: number;
  clauses: number;
  audit: number;
  warnings: number;
}

export interface ContractTask {
  taskId: string;
  fileName: string;
  status: TaskStatus;
  createdAt: string;
  modelName: string;
  confidenceOverview: ConfidenceOverview;
  progressPercent: number;
  currentStage?: string | null;
  stageDetail?: string | null;
  elapsedMs?: number;
}

export interface ContractAnalysisResult {
  task: ContractTask;
  pages: ContractPage[];
  sections: ContractSection[];
  clauses: ClauseTag[];
  keyFacts: KeyFact[];
}
