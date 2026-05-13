from __future__ import annotations

from app.services.document_service import DocumentPreparation


class Planner:
    def build_plan(self, document: DocumentPreparation) -> list[str]:
        plan = ["receive-file", "detect-file-type", "document-preprocess"]
        if document.recommended_pipeline in {"ocr-first", "mock-sample"}:
            plan.append("ocr")
        else:
            plan.append("text-extract")
        plan.extend(
            [
                "section-reconstruction",
                "clause-tagging",
                "key-info-extraction",
                "relation-analysis",
                "audit-focus-generation",
                "verification",
                "evidence-mapping",
                "confidence-score",
            ]
        )
        return plan
