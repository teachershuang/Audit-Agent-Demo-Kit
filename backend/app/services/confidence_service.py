from __future__ import annotations

from statistics import mean

from app.schemas.audit import AuditFocus
from app.schemas.contract import ClauseTag, ConfidenceOverview, ContractSection


class ConfidenceService:
    def summarize(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        audit_focuses: list[AuditFocus],
    ) -> ConfidenceOverview:
        section_conf = mean([item.confidence for item in sections]) if sections else 0.0
        clause_conf = mean([item.confidence for item in clauses]) if clauses else 0.0
        audit_conf = mean([item.confidence for item in audit_focuses]) if audit_focuses else 0.0
        warnings = len([item for item in clauses if item.needHumanReview]) + len(
            [item for item in audit_focuses if item.riskLevel == "pending_verification"]
        )
        overall = round((section_conf * 0.32) + (clause_conf * 0.38) + (audit_conf * 0.30), 2)
        return ConfidenceOverview(
            overall=overall,
            sections=round(section_conf, 2),
            clauses=round(clause_conf, 2),
            audit=round(audit_conf, 2),
            warnings=warnings,
        )
