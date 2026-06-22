from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image

from app.logging_utils import app_logger, json_dumps
from app.schemas.contract import ClauseTag, ContractAnalysisResult, EvidenceRef, KeyFact
from app.schemas.review import ReviewIssue
from app.storage.local_store import LocalStore


class ReportPreviewService:
    def __init__(self, *, local_store: LocalStore, report_store, storage_root: Path) -> None:
        self.local_store = local_store
        self.report_store = report_store
        self.storage_root = storage_root

    def build_report_payload(self, contract_id: str) -> dict[str, Any] | None:
        report = self.report_store.get_report(contract_id)
        schema = self.report_store.get_schema(contract_id)
        if report is None or schema is None:
            return None
        source_record = self.local_store.get_task(schema.source_task_id)
        result = source_record.result
        issues = [self._build_issue_payload(contract_id, issue, result) for issue in report.issues]
        payload = report.model_dump()
        payload["source_task_id"] = schema.source_task_id
        payload["issues"] = issues
        return payload

    def get_issue_snippet_path(self, contract_id: str, issue_id: str) -> Path | None:
        report = self.report_store.get_report(contract_id)
        schema = self.report_store.get_schema(contract_id)
        if report is None or schema is None:
            return None
        source_record = self.local_store.get_task(schema.source_task_id)
        if source_record.result is None:
            return None
        issue = next((item for item in report.issues if item.id == issue_id), None)
        if issue is None:
            return None
        preview = self._resolve_issue_preview(contract_id, issue, source_record.result)
        image_url = preview.get("image_url")
        if not image_url:
            return None
        return self._snippet_path(schema.source_task_id, issue_id)

    def _build_issue_payload(self, contract_id: str, issue: ReviewIssue, result: ContractAnalysisResult | None) -> dict[str, Any]:
        payload = issue.model_dump()
        payload["preview"] = self._resolve_issue_preview(contract_id, issue, result) if result is not None else None
        return payload

    def _resolve_issue_preview(self, contract_id: str, issue: ReviewIssue, result: ContractAnalysisResult) -> dict[str, Any]:
        if issue.extra.get("no_direct_evidence"):
            return {
                "note": "这是缺失或规则类问题，待审合同中没有可直接定位的对应原文证据。",
                "page": None,
                "excerpt": None,
                "image_url": None,
                "clause_title": None,
                "fact_label": None,
                "evidence_id": None,
            }

        target = self._pick_target(issue, result)
        if target is None:
            return {
                "note": "未能定位到对应原文。",
                "page": None,
                "excerpt": None,
                "image_url": None,
                "clause_title": None,
                "fact_label": None,
                "evidence_id": None,
            }

        page, evidence, clause, fact = target
        snippet_url = self._ensure_snippet(contract_id, result.task.taskId, issue.id, page, evidence)
        return {
            "page": page.page,
            "page_title": page.title,
            "clause_title": clause.title if clause else None,
            "fact_label": fact.label if fact else None,
            "evidence_id": evidence.id,
            "excerpt": evidence.text[:260],
            "image_url": snippet_url,
        }

    def _pick_target(
        self,
        issue: ReviewIssue,
        result: ContractAnalysisResult,
    ) -> tuple[Any, EvidenceRef, ClauseTag | None, KeyFact | None] | None:
        evidence_index = {evidence.id: (page, evidence) for page in result.pages for evidence in page.evidences}
        tokens = self._tokens(
            issue.problem,
            issue.clause_location,
            issue.source_rule_name,
            issue.basis_template_detail.get("matched_clause_title") if issue.basis_template_detail else None,
        )

        clause_candidates: list[tuple[float, ClauseTag]] = []
        for clause in result.clauses:
            haystack = "\n".join([clause.title, clause.summary, clause.rawText, clause.label, clause.coreLabel])
            score = self._score_text_match(tokens, haystack)
            location_hint = self._location_hint(issue.clause_location)
            if location_hint and location_hint in haystack:
                score += 5
            if issue.problem and clause.title and clause.title in issue.problem:
                score += 4
            if issue.basis_template_detail:
                matched_title = str(issue.basis_template_detail.get("matched_clause_title") or "")
                if matched_title and matched_title in haystack:
                    score += 6
            if score > 0:
                clause_candidates.append((score, clause))

        clause_candidates.sort(key=lambda item: item[0], reverse=True)
        for _, clause in clause_candidates[:6]:
            evidence_pair = evidence_index.get(clause.evidenceId)
            if evidence_pair:
                page, evidence = evidence_pair
                return page, evidence, clause, None

        fact_candidates: list[tuple[float, KeyFact]] = []
        for fact in result.keyFacts:
            haystack = "\n".join([fact.label, fact.value, fact.notes or ""])
            score = self._score_text_match(tokens, haystack)
            location_hint = self._location_hint(issue.clause_location)
            if location_hint and location_hint in haystack:
                score += 4
            if score > 0:
                fact_candidates.append((score, fact))
        fact_candidates.sort(key=lambda item: item[0], reverse=True)
        for _, fact in fact_candidates[:4]:
            if fact.evidenceId and fact.evidenceId in evidence_index:
                page, evidence = evidence_index[fact.evidenceId]
                return page, evidence, None, fact

        return None

    @staticmethod
    def _tokens(*values: str | None) -> list[str]:
        tokens: list[str] = []
        for value in values:
            if not value:
                continue
            normalized = re.sub(r"[\s:：，。；;（）()【】\[\]/\\\-]+", " ", value)
            parts = [part.strip() for part in normalized.split(" ") if len(part.strip()) >= 2]
            tokens.extend(parts[:24])
        deduped: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            if token not in seen:
                deduped.append(token)
                seen.add(token)
        return deduped

    @staticmethod
    def _location_hint(value: str | None) -> str | None:
        if not value:
            return None
        if ":" in value:
            return value.split(":", 1)[1].strip()
        if "：" in value:
            return value.split("：", 1)[1].strip()
        return value.strip() or None

    @staticmethod
    def _score_text_match(tokens: list[str], haystack: str) -> float:
        score = 0.0
        for token in tokens:
            if token and token in haystack:
                score += min(len(token), 8)
        return score

    def _ensure_snippet(self, contract_id: str, source_task_id: str, issue_id: str, page, evidence: EvidenceRef) -> str | None:
        snippet_path = self._snippet_path(source_task_id, issue_id)
        if not snippet_path.exists():
            image_path = Path(page.imageLocalPath or "")
            if not image_path.exists():
                image_path = self.storage_root / source_task_id / "pages" / f"page_{page.page:03d}.png"
            if not image_path.exists():
                return None
            snippet_path.parent.mkdir(parents=True, exist_ok=True)
            self._create_snippet(image_path, snippet_path, evidence.bbox)
            app_logger.debug(
                json_dumps(
                    {
                        "event": "report_issue_snippet_created",
                        "contractId": contract_id,
                        "issueId": issue_id,
                        "page": page.page,
                        "sourceImage": str(image_path),
                        "snippetPath": str(snippet_path),
                    }
                )
            )
        return f"/api/base/contracts/{contract_id}/issues/{issue_id}/snippet"

    def _snippet_path(self, source_task_id: str, issue_id: str) -> Path:
        return self.storage_root / source_task_id / "report-snippets" / f"{issue_id}.png"

    @staticmethod
    def _create_snippet(source_path: Path, target_path: Path, bbox: tuple[int, int, int, int]) -> None:
        image = Image.open(source_path).convert("RGB")
        x, y, width, height = bbox
        padding_x = max(48, int(width * 0.2))
        padding_y = max(48, int(height * 0.35))
        left = max(0, x - padding_x)
        top = max(0, y - padding_y)
        right = min(image.width, x + width + padding_x)
        bottom = min(image.height, y + height + padding_y)

        min_width = min(image.width, 900)
        min_height = min(image.height, 460)
        if right - left < min_width:
            shortage = min_width - (right - left)
            left = max(0, left - shortage // 2)
            right = min(image.width, right + shortage - shortage // 2)
        if bottom - top < min_height:
            shortage = min_height - (bottom - top)
            top = max(0, top - shortage // 2)
            bottom = min(image.height, bottom + shortage - shortage // 2)

        cropped = image.crop((left, top, right, bottom))
        cropped.save(target_path, format="PNG")
