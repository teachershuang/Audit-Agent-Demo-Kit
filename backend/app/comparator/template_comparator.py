from __future__ import annotations

from app.comparator.clause_matcher import clause_similarity
from app.schemas.clause import ClauseRecord
from app.schemas.contract import ClauseTag


class TemplateComparator:
    def compare(self, contract_clauses: list[ClauseTag], template_clauses: list[ClauseRecord]) -> dict:
        matched_contract_ids: set[str] = set()
        missing: list[dict] = []
        weakened: list[dict] = []

        for template_clause in template_clauses:
            best_clause = None
            best_score = 0.0
            for contract_clause in contract_clauses:
                score = clause_similarity(
                    template_clause.title,
                    template_clause.content,
                    contract_clause.title,
                    contract_clause.rawText,
                )
                if template_clause.clause_type == getattr(contract_clause, "coreLabel", ""):
                    score += 0.2
                if template_clause.clause_type == "general" and template_clause.title in contract_clause.title:
                    score += 0.2
                if score > best_score:
                    best_score = score
                    best_clause = contract_clause
            if best_clause is None or best_score < 0.42:
                missing.append(
                    {
                        "template_clause_id": template_clause.id,
                        "title": template_clause.title,
                        "clause_type": template_clause.clause_type,
                        "page": template_clause.page_start,
                    }
                )
                continue
            matched_contract_ids.add(best_clause.id)
            contract_length = max(1, len(best_clause.rawText))
            template_length = max(1, len(template_clause.content))
            if best_score < 0.62 or contract_length / template_length < 0.35:
                weakened.append(
                    {
                        "template_clause_id": template_clause.id,
                        "contract_clause_id": best_clause.id,
                        "title": template_clause.title,
                        "clause_type": template_clause.clause_type,
                        "score": round(best_score, 4),
                    }
                )

        additional = [
            {
                "contract_clause_id": clause.id,
                "title": clause.title,
                "page": clause.page,
            }
            for clause in contract_clauses
            if clause.id not in matched_contract_ids
        ]
        return {
            "missing": missing,
            "weakened": weakened,
            "additional": additional,
        }
