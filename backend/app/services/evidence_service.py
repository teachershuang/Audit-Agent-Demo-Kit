from __future__ import annotations

from app.schemas.contract import ContractAnalysisResult, EvidenceRef


class EvidenceService:
    def build_index(self, result: ContractAnalysisResult) -> dict[str, EvidenceRef]:
        return {
            evidence.id: evidence
            for page in result.pages
            for evidence in page.evidences
        }
