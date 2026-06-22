from __future__ import annotations

import asyncio
import json
import re
from difflib import SequenceMatcher
from typing import Any

from app.config import Settings
from app.prompts.evidence import build_grounding_prompt
from app.schemas.contract import ClauseTag, ContractAnalysisResult, ContractPage, ContractSection, EvidenceRef, KeyFact
from app.services.qwen_service import QwenService


class EvidenceService:
    def __init__(
        self,
        qwen_service: QwenService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.qwen_service = qwen_service
        self.settings = settings

    @property
    def parallelism(self) -> int:
        return max(1, getattr(self.settings, "qwen_parallel_requests", 4))

    async def attach_evidences(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        key_facts: list[KeyFact],
    ) -> None:
        for page in pages:
            page.evidences = []

        section_blocks = {}
        clause_blocks = await self._ground_clauses(pages, clauses)
        fact_blocks = {}

        for section in sections:
            if section.id in section_blocks:
                section.blockIds = section_blocks[section.id]
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
            if clause.id in clause_blocks:
                clause.blockIds = clause_blocks[clause.id]
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
            grounded_ids = fact_blocks.get(fact.id, [])
            evidence = self._locate_evidence(
                pages=pages,
                target_text=f"{fact.label} {fact.value}",
                source_type="fact",
                source_id=fact.id,
                page_hint=fact.page,
                accent="cyan",
                block_ids=grounded_ids,
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

    async def _ground_sections(
        self,
        pages: list[ContractPage],
        sections: list[ContractSection],
    ) -> dict[str, list[str]]:
        candidates = [
            {
                "candidateId": section.id,
                "page": section.page,
                "title": section.title,
                "summary": section.summary,
                "snippet": f"{section.title}\n{section.summary}",
            }
            for section in sections
        ]
        return await self._ground_candidates(pages, candidates, top_key="sections", item_kind="section")

    async def _ground_clauses(
        self,
        pages: list[ContractPage],
        clauses: list[ClauseTag],
    ) -> dict[str, list[str]]:
        candidates = [
            {
                "candidateId": clause.id,
                "page": clause.page,
                "title": clause.label,
                "summary": clause.summary,
                "snippet": clause.rawText or clause.summary,
            }
            for clause in clauses
        ]
        return await self._ground_candidates(pages, candidates, top_key="clauses", item_kind="clause")

    async def _ground_key_facts(
        self,
        pages: list[ContractPage],
        key_facts: list[KeyFact],
    ) -> dict[str, list[str]]:
        candidates = [
            {
                "candidateId": fact.id,
                "page": fact.page,
                "title": fact.label,
                "summary": fact.value,
                "snippet": f"{fact.label}: {fact.value}",
            }
            for fact in key_facts
        ]
        return await self._ground_candidates(pages, candidates, top_key="facts", item_kind="fact")

    async def _ground_candidates(
        self,
        pages: list[ContractPage],
        candidates: list[dict[str, Any]],
        top_key: str,
        item_kind: str,
    ) -> dict[str, list[str]]:
        if not self.qwen_service or not candidates:
            return {}

        batch_size = 6 if item_kind == "clause" else 8
        radius = 0 if item_kind in {"clause", "fact"} else 1
        batches = self._chunk_items(candidates, batch_size)
        tasks = [self._ground_batch(pages, batch, top_key=top_key, item_kind=item_kind, radius=radius) for batch in batches]
        results = await self._gather_limited(tasks, min(self.parallelism, max(1, len(tasks))))
        merged: dict[str, list[str]] = {}
        for batch_map in results:
            for candidate_id, block_ids in batch_map.items():
                if block_ids:
                    merged[candidate_id] = block_ids
        return merged

    async def _ground_batch(
        self,
        pages: list[ContractPage],
        batch: list[dict[str, Any]],
        top_key: str,
        item_kind: str,
        radius: int,
    ) -> dict[str, list[str]]:
        page_scope = self._candidate_page_scope(batch, pages, radius=radius)
        if not page_scope:
            page_scope = pages[: min(3, len(pages))]
        try:
            prompt = build_grounding_prompt(
                batch=batch,
                page_scope=self._grounding_pages_payload(page_scope),
                top_key=top_key,
                item_kind=item_kind,
            )
            payload = await self.qwen_service.chat_json(
                system_prompt=prompt.system,
                user_prompt=prompt.user,
                schema={"type": "object"},
                timeout=120,
            )
        except Exception:
            return {}

        grounded = payload.get(top_key)
        if not isinstance(grounded, list):
            return {}
        results: dict[str, list[str]] = {}
        for item in grounded:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidateId") or "").strip()
            if not candidate_id:
                continue
            block_ids = item.get("blockIds") or item.get("evidenceBlockIds") or item.get("supportingBlockIds") or []
            normalized = self._normalize_block_ids(block_ids)
            if normalized:
                results[candidate_id] = normalized
        return results

    @staticmethod
    def _grounding_pages_payload(pages: list[ContractPage]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for page in pages:
            blocks = [
                {
                    "id": block.id,
                    "text": block.text.strip()[:220],
                    "x": block.x,
                    "y": block.y,
                    "width": block.width,
                    "height": block.height,
                    "emphasis": block.emphasis,
                }
                for block in page.blocks[:100]
                if block.text.strip()
            ]
            payload.append(
                {
                    "page": page.page,
                    "title": page.title,
                    "pageText": "\n".join(block["text"] for block in blocks)[:6000],
                    "blocks": blocks,
                }
            )
        return payload

    @staticmethod
    def _candidate_page_scope(
        items: list[dict[str, Any]],
        pages: list[ContractPage],
        radius: int,
    ) -> list[ContractPage]:
        page_numbers: set[int] = set()
        max_page = max((page.page for page in pages), default=1)
        for item in items:
            try:
                page = int(item.get("page"))
            except Exception:
                page = None
            if page is None:
                continue
            for candidate in range(max(1, page - radius), min(max_page, page + radius) + 1):
                page_numbers.add(candidate)
        if not page_numbers:
            return pages[: min(3, len(pages))]
        return [page for page in pages if page.page in page_numbers]

    @staticmethod
    def _normalize_block_ids(candidate: Any) -> list[str]:
        if isinstance(candidate, list):
            values = [str(item).strip() for item in candidate if str(item).strip()]
        elif isinstance(candidate, str):
            values = [part.strip() for part in re.split(r"[,;\s]+", candidate) if part.strip()]
        else:
            values = []
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    async def _gather_limited(self, coroutines: list[Any], limit: int) -> list[Any]:
        semaphore = asyncio.Semaphore(max(1, limit))

        async def runner(coro: Any) -> Any:
            async with semaphore:
                return await coro

        return await asyncio.gather(*(runner(coro) for coro in coroutines))

    @staticmethod
    def _chunk_items(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        return [items[index : index + size] for index in range(0, len(items), max(1, size))]

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
