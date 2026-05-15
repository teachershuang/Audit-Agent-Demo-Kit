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
        index: dict[str, EvidenceRef] = {}
        for page in result.pages:
            for evidence in page.evidences:
                current = index.get(evidence.id)
                if current is None or evidence.isPrimary:
                    index[evidence.id] = evidence
        return index

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
            page_hint=page_hint,
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
        page_hint: int,
        accent: str,
    ) -> EvidenceRef | None:
        if not block_ids:
            return None
        order = {block_id: index for index, block_id in enumerate(block_ids)}
        resolved: list[tuple[ContractPage, object]] = []
        for page in pages:
            for block in page.blocks:
                if block.id in order:
                    resolved.append((page, block))
        if not resolved:
            return None
        resolved.sort(key=lambda item: order[item[1].id])

        segments: list[list[tuple[ContractPage, object]]] = []
        current_segment: list[tuple[ContractPage, object]] = []
        for item in resolved:
            if not current_segment:
                current_segment = [item]
                continue
            previous_page, previous_block = current_segment[-1]
            current_page, current_block = item
            if self._should_split_segment(previous_page, previous_block, current_page, current_block):
                segments.append(current_segment)
                current_segment = [item]
            else:
                current_segment.append(item)
        if current_segment:
            segments.append(current_segment)

        evidence_id = f"ev_{source_id}"
        for page in pages:
            page.evidences = [item for item in page.evidences if item.id != evidence_id]

        primary_index = self._pick_primary_segment_index(segments, page_hint)
        primary_evidence: EvidenceRef | None = None
        total = len(segments)
        for index, segment in enumerate(segments):
            page = segment[0][0]
            blocks = [block for _, block in segment]
            evidence = EvidenceRef(
                id=evidence_id,
                page=page.page,
                bbox=tuple(self._merge_bbox(blocks)),
                text="\n".join(block.text.strip() for block in blocks if block.text.strip())[:1200],
                sourceType=source_type,
                sourceId=source_id,
                segmentIndex=index,
                segmentCount=total,
                isPrimary=index == primary_index,
                accent=accent,
            )
            page.evidences.append(evidence)
            if evidence.isPrimary:
                primary_evidence = evidence
        return primary_evidence

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
            segmentIndex=0,
            segmentCount=1,
            isPrimary=True,
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
    def _should_split_segment(previous_page, previous_block, current_page, current_block) -> bool:
        if previous_page.page != current_page.page:
            return True
        previous_bottom = previous_block.y + (previous_block.height or 24)
        current_top = current_block.y
        vertical_gap = current_top - previous_bottom
        horizontal_shift = abs(current_block.x - previous_block.x)
        tall_reference = max(previous_block.height or 24, current_block.height or 24)
        if vertical_gap > tall_reference * 2.6:
            return True
        if vertical_gap > tall_reference * 1.4 and horizontal_shift > max(previous_block.width, current_block.width) * 0.35:
            return True
        return False

    @staticmethod
    def _pick_primary_segment_index(segments, page_hint: int) -> int:
        best_index = 0
        best_score = float("-inf")
        for index, segment in enumerate(segments):
            page = segment[0][0]
            blocks = [block for _, block in segment]
            text_len = sum(len((block.text or "").strip()) for block in blocks)
            score = text_len + len(blocks) * 20
            if page.page == page_hint:
                score += 200
            if score > best_score:
                best_score = score
                best_index = index
        return best_index

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
