from __future__ import annotations

from typing import Iterable

from app.schemas.agent import AgentStep, AgentStepStatus
from app.schemas.audit import AuditFocus, RiskLevel, VerificationItem, VerificationStatus
from app.schemas.review import ReviewReport


class MainProjectReviewBridge:
    def build_focuses(self, report: ReviewReport) -> list[AuditFocus]:
        focuses: list[AuditFocus] = []
        for issue in report.issues:
            focuses.append(
                AuditFocus(
                    id=f"kb_{issue.id}",
                    title=issue.problem,
                    focusSource="knowledge_base_rule_check",
                    matchedRelationIds=[],
                    riskLevel=self._risk_from_severity(issue.severity),
                    reason=f"制度底座命中：{issue.problem}",
                    evidenceClauseIds=[],
                    locationText=issue.clause_location or "制度底座定位",
                    confidence=issue.confidence,
                    dependsOn=[item.get("title", "") for item in issue.basis_policy_details if item.get("title")],
                    currentBasis=self._current_basis(issue),
                    futureTools=["knowledge_base_service", "template_comparator", "rule_library"],
                    modelOnly=False,
                    humanReviewSuggestion=issue.suggestion,
                    ruleId=issue.source_rule_id,
                    engineStatus="knowledge_base_hit",
                    detail={
                        "basisPolicyIds": issue.basis_policy,
                        "basisPolicyDetails": issue.basis_policy_details,
                        "basisTemplate": issue.basis_template_detail,
                        "sourceRuleId": issue.source_rule_id,
                        "sourceRuleName": issue.source_rule_name,
                        "department": issue.department,
                    },
                )
            )
        return focuses

    def build_verification_items(self, report: ReviewReport) -> list[VerificationItem]:
        items: list[VerificationItem] = []
        for issue in report.issues:
            items.append(
                VerificationItem(
                    id=f"kb_verify_{issue.id}",
                    name=issue.problem,
                    method="knowledge_base / template_compare / rule_library",
                    status=self._verification_from_severity(issue.severity),
                    description=issue.suggestion,
                    relatedClauseIds=[],
                    relatedEvidenceIds=[],
                    needExternalTool=False,
                    source="knowledge_base",
                    ruleId=issue.source_rule_id,
                    engineStatus="knowledge_base_hit",
                    detail={
                        "basisPolicyDetails": issue.basis_policy_details,
                        "basisTemplate": issue.basis_template_detail,
                        "sourceRuleName": issue.source_rule_name,
                    },
                )
            )
        return items

    def build_agent_step(self, report: ReviewReport) -> AgentStep:
        return AgentStep(
            id="step_011",
            name="制度底座校验",
            status=AgentStepStatus.SUCCESS,
            durationMs=220,
            inputSummary=report.contract_id,
            outputSummary=f"制度底座返回 {len(report.issues)} 个审查问题",
            tool="knowledge_base_review_pipeline",
            success=True,
            errorMessage=None,
        )

    @staticmethod
    def merge_focuses(*groups: Iterable[AuditFocus]) -> list[AuditFocus]:
        seen: set[str] = set()
        merged: list[AuditFocus] = []
        for group in groups:
            for item in group:
                if item.id in seen:
                    continue
                seen.add(item.id)
                merged.append(item)
        return merged

    @staticmethod
    def merge_verification_items(*groups: Iterable[VerificationItem]) -> list[VerificationItem]:
        seen: set[str] = set()
        merged: list[VerificationItem] = []
        for group in groups:
            for item in group:
                if item.id in seen:
                    continue
                seen.add(item.id)
                merged.append(item)
        return merged

    @staticmethod
    def _risk_from_severity(severity: str) -> RiskLevel:
        if severity == "must_modify":
            return RiskLevel.HIGH
        if severity == "suggest_modify":
            return RiskLevel.MEDIUM
        return RiskLevel.PENDING_VERIFICATION

    @staticmethod
    def _verification_from_severity(severity: str) -> VerificationStatus:
        if severity == "must_modify":
            return VerificationStatus.FAIL
        if severity == "suggest_modify":
            return VerificationStatus.WARNING
        return VerificationStatus.EXTERNAL_PENDING

    @staticmethod
    def _current_basis(issue) -> str:
        policy_titles = [item.get("title", "") for item in issue.basis_policy_details if item.get("title")]
        template_title = issue.basis_template_detail.get("template_name") if issue.basis_template_detail else None
        parts = []
        if policy_titles:
            parts.append(f"制度依据：{' / '.join(policy_titles[:3])}")
        if template_title:
            parts.append(f"范本依据：{template_title}")
        if issue.source_rule_name:
            parts.append(f"规则：{issue.source_rule_name}")
        return "；".join(parts) or "制度底座综合校验结果"
