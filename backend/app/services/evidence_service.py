from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.schemas.contract import ClauseTag, ContractAnalysisResult, ContractPage, ContractSection, EvidenceRef, KeyFact


class EvidenceService:
    def attach_evidences(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        key_facts: list[KeyFact],
    ) -> None:
        for section in sections:
            evidence = self._locate_evidence(
                pages=pages,
                target_text=f"{section.title} {section.summary}",
                source_type="section",
                source_id=section.id,
                page_hint=section.page,
                accent="cyan",
                block_ids=section.blockIds,
            )
            section.evidenceId = evidence.id

        for clause in clauses:
            evidence = self._locate_evidence(
                pages=pages,
                target_text=clause.rawText or clause.summary,
                source_type="clause",
                source_id=clause.id,
                page_hint=clause.page,
                accent="amber" if clause.needHumanReview else "cyan",
                block_ids=clause.blockIds,
            )
            clause.evidenceId = evidence.id

        for fact in key_facts:
            evidence = self._locate_text(
                pages=pages,
                target_text=f"{fact.label} {fact.value}",
                source_type="fact",
                source_id=fact.id,
                page_hint=fact.page,
                accent="cyan",
            )
            fact.evidenceId = evidence.id

    def build_index(self, result: ContractAnalysisResult) -> dict[str, EvidenceRef]:
        return {evidence.id: evidence for page in result.pages for evidence in page.evidences}

    def _locate_evidence(
        self,
        pages: list[ContractPage],
        target_text: str,
        source_type: str,
        source_id: str,
        page_hint: int,
        accent: str,
        block_ids: list[str] | None = None,
    ) -> EvidenceRef:
        grounded = self._locate_blocks(
            pages=pages,
            block_ids=block_ids or [],
            source_type=source_type,
            source_id=source_id,
            accent=accent,
        )
        if grounded is not None:
            return grounded
        return self._locate_text(
            pages=pages,
            target_text=target_text,
            source_type=source_type,
            source_id=source_id,
            page_hint=page_hint,
            accent=accent,
        )

    def _locate_blocks(
        self,
        pages: list[ContractPage],
        block_ids: list[str],
        source_type: str,
        source_id: str,
        accent: str,
    ) -> EvidenceRef | None:
        if not block_ids:
            return None
        for page in pages:
            matched = [block for block in page.blocks if block.id in block_ids]
            if not matched:
                continue
            evidence = EvidenceRef(
                id=f"ev_{source_id}",
                page=page.page,
                bbox=tuple(self._merge_bbox(matched)),
                text="\n".join(block.text.strip() for block in matched if block.text.strip())[:1200],
                sourceType=source_type,
                sourceId=source_id,
                accent=accent,
            )
            page.evidences = [item for item in page.evidences if item.id != evidence.id]
            page.evidences.append(evidence)
            return evidence
        return None

    def _locate_text(
        self,
        pages: list[ContractPage],
        target_text: str,
        source_type: str,
        source_id: str,
        page_hint: int,
        accent: str,
    ) -> EvidenceRef:
        best_page = pages[0]
        best_bbox = [40, 40, 200, 40]
        best_text = target_text[:120]
        best_score = -1.0
        normalized_target = self._normalize(target_text)

        for page in pages:
            blocks = page.blocks
            for start in range(len(blocks)):
                for size in range(1, min(4, len(blocks) - start) + 1):
                    window = blocks[start : start + size]
                    candidate_text = " ".join(block.text for block in window).strip()
                    if not candidate_text:
                        continue
                    score = self._score_match(normalized_target, self._normalize(candidate_text))
                    if page.page == page_hint:
                        score += 0.06
                    if score > best_score:
                        best_score = score
                        best_page = page
                        best_text = candidate_text
                        best_bbox = self._merge_bbox(window)

        evidence = EvidenceRef(
            id=f"ev_{source_id}",
            page=best_page.page,
            bbox=(best_bbox[0], best_bbox[1], best_bbox[2], best_bbox[3]),
            text=best_text,
            sourceType=source_type,
            sourceId=source_id,
            accent=accent,
        )
        best_page.evidences = [item for item in best_page.evidences if item.id != evidence.id]
        best_page.evidences.append(evidence)
        return evidence

    @staticmethod
    def _merge_bbox(blocks) -> list[int]:
        min_x = min(block.x for block in blocks)
        min_y = min(block.y for block in blocks)
        max_x = max(block.x + block.width for block in blocks)
        max_y = max(block.y + (block.height or 24) for block in blocks)
        return [min_x, min_y, max_x - min_x, max_y - min_y]

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[\s\W_]+", "", text or "").lower()

    @staticmethod
    def _score_match(target: str, candidate: str) -> float:
        if not target or not candidate:
            return 0.0
        if target in candidate or candidate in target:
            return 0.95
        return SequenceMatcher(a=target[:400], b=candidate[:400]).ratio()
