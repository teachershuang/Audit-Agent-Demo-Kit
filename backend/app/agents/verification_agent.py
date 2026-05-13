from __future__ import annotations

from app.mock.sample_result import build_mock_verification_items
from app.schemas.audit import AuditFocus, VerificationItem
from app.schemas.contract import ClauseTag, ContractSection


class VerificationAgent:
    def verify(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        audit_focuses: list[AuditFocus],
    ) -> list[VerificationItem]:
        _ = sections, clauses, audit_focuses
        return build_mock_verification_items()
