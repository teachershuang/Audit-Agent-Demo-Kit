from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import fitz

from app.embedding.embedding_client import EmbeddingClient
from app.llm.llm_client import LLMClient
from app.parser.docx_parser import DOCXParser
from app.parser.pdf_parser import PDFParser
from app.redis_store.clause_store import ClauseStore
from app.redis_store.document_store import DocumentStore
from app.redis_store.rule_store import RuleStore
from app.rule_engine.business_rules import BUSINESS_RULES
from app.rule_engine.finance_rules import FINANCE_RULES
from app.rule_engine.legal_rules import LEGAL_RULES
from app.schemas.clause import ClauseRecord
from app.schemas.document import DocumentRecord, TemplateCatalogItem
from app.schemas.rule import RuleRecord
from app.splitter.clause_splitter import ClauseSplitter
from app.splitter.policy_splitter import PolicySplitter
from app.splitter.template_splitter import TemplateSplitter


class KnowledgeBaseService:
    def __init__(
        self,
        *,
        storage_root: Path,
        document_store: DocumentStore,
        clause_store: ClauseStore,
        rule_store: RuleStore,
        embedding_client: EmbeddingClient,
        llm_client: LLMClient,
        pdf_parser: PDFParser,
        docx_parser: DOCXParser,
        policy_splitter: PolicySplitter,
        template_splitter: TemplateSplitter,
        clause_splitter: ClauseSplitter,
    ) -> None:
        self.storage_root = storage_root
        self.document_store = document_store
        self.clause_store = clause_store
        self.rule_store = rule_store
        self.embedding_client = embedding_client
        self.llm_client = llm_client
        self.pdf_parser = pdf_parser
        self.docx_parser = docx_parser
        self.policy_splitter = policy_splitter
        self.template_splitter = template_splitter
        self.clause_splitter = clause_splitter
        self.rule_catalog = BUSINESS_RULES + LEGAL_RULES + FINANCE_RULES

    async def ingest_document(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        doc_type: str,
        version: str,
        issuer: str | None,
        effective_date: str | None,
        effective_ts: int,
        category: str | None,
        confidential_level: str,
    ) -> tuple[DocumentRecord, list[ClauseRecord], list[RuleRecord]]:
        doc_id = f"doc_{uuid4().hex[:12]}"
        file_path = self._persist_file(doc_id, file_name, file_bytes)
        parsed = self._parse(file_path)
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        document = DocumentRecord(
            id=doc_id,
            name=file_name,
            doc_type=doc_type,
            category=category,
            version=version,
            issuer=issuer,
            status="effective",
            effective_date=effective_date,
            effective_ts=effective_ts,
            abolish_ts=99991231,
            file_hash=file_hash,
            source_file=str(file_path),
            confidential_level=confidential_level,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            source_kind="template_collection" if doc_type == "template" else "policy_file",
        )

        clauses: list[ClauseRecord] = []
        generated_rules: list[RuleRecord] = []
        if doc_type == "policy":
            policy_clauses = self.policy_splitter.split(parsed["text"], doc_id, effective_ts, 99991231)
            clauses = [ClauseRecord(**item, embedding=await self.embedding_client.embed_text(item["title"] + "\n" + item["content"])) for item in policy_clauses]
            generated_rules = self._generate_rule_drafts(document, clauses)
        elif doc_type == "template":
            catalog = self.template_splitter.extract_catalog(parsed)
            resolved = self.template_splitter.resolve_template_ranges(parsed, catalog)
            clause_items: list[ClauseRecord] = []
            for item in resolved:
                template_text = self.template_splitter.template_text(parsed, item["start_page"], item["end_page"])
                split_clauses = self.clause_splitter.split_template_text(
                    text=template_text,
                    document_id=doc_id,
                    template_id=item["template_id"],
                    template_name=item["template_name"],
                    category_lv1=item["category_lv1"],
                    category_lv2=item["category_lv2"],
                    effective_ts=effective_ts,
                    abolish_ts=99991231,
                    page_start=item["start_page"],
                    page_end=item["end_page"],
                )
                for clause in split_clauses:
                    clause_items.append(
                        ClauseRecord(
                            **clause,
                            embedding=await self.embedding_client.embed_text(clause["title"] + "\n" + clause["content"]),
                        )
                    )
            clauses = clause_items
            document = document.model_copy(
                update={
                    "template_count": len(self._dedupe_template_catalog(resolved)),
                    "template_catalog": [TemplateCatalogItem(**item) for item in self._dedupe_template_catalog(resolved)],
                }
            )

        self.document_store.save(document)
        if clauses:
            self.clause_store.save_many(clauses)
        for rule in generated_rules:
            self.rule_store.save(rule)
        return document, clauses, generated_rules

    def abolish_document(self, doc_id: str, abolish_ts: int, abolish_date: str | None) -> DocumentRecord | None:
        document = self.document_store.update_fields(
            doc_id,
            status="abolished",
            abolish_ts=abolish_ts,
            abolish_date=abolish_date,
            current_version_flag=False,
        )
        if document is not None:
            self.clause_store.update_document_status(doc_id, status="abolished", abolish_ts=abolish_ts)
        return document

    def replace_document(self, old_doc_id: str, new_doc_id: str) -> tuple[DocumentRecord | None, DocumentRecord | None]:
        old_doc = self.document_store.update_fields(
            old_doc_id,
            status="superseded",
            replaced_by=new_doc_id,
            current_version_flag=False,
        )
        new_doc = self.document_store.update_fields(new_doc_id, current_version_flag=True)
        if old_doc is not None:
            self.clause_store.update_document_status(old_doc_id, status="superseded", abolish_ts=int(datetime.now().strftime("%Y%m%d")))
        return old_doc, new_doc

    def document_metadata(self, doc_id: str, *, include_clauses: bool = False) -> dict | None:
        document = self.document_store.get(doc_id)
        if document is None:
            return None
        clauses = self._dedupe_clauses(self.clause_store.list(document_id=doc_id, include_embedding=False))
        rules = self._dedupe_rules(self.rule_store.list_by_source_document(doc_id))
        effective_clause_count = sum(1 for clause in clauses if clause.status in {"effective", "partially_effective"})
        enabled_rule_count = sum(1 for rule in rules if rule.enabled)
        template_catalog = self._enrich_template_catalog([entry.model_dump() for entry in document.template_catalog], clauses)
        document_payload = document.model_dump()
        document_payload["template_catalog"] = template_catalog
        return {
            "document": document_payload,
            "summary": {
                "clause_count": len(clauses),
                "effective_clause_count": effective_clause_count,
                "rule_count": len(rules),
                "enabled_rule_count": enabled_rule_count,
                "template_count": document.template_count,
                "source_kind": document.source_kind,
                "current_version_flag": document.current_version_flag,
            },
            "version_context": self._document_version_context(document),
            "clauses": [self._build_clause_list_item(clause) for clause in clauses] if include_clauses else [],
            "rules": [rule.model_dump() for rule in rules],
        }

    def document_clause_list(self, doc_id: str) -> list[dict] | None:
        document = self.document_store.get(doc_id)
        if document is None:
            return None
        clauses = self._dedupe_clauses(self.clause_store.list(document_id=doc_id, include_embedding=False))
        return [self._build_clause_list_item(clause) for clause in clauses]

    def clause_metadata(self, clause_id: str) -> dict | None:
        clause = self.clause_store.get(clause_id)
        if clause is None:
            return None
        document = self.document_store.get(clause.document_id)
        linked_rules = self._dedupe_rules([rule for rule in self.rule_store.list() if clause_id in rule.basis_policy])
        return {
            "clause": self._build_clause_summary(clause, document=document, content_chars=4000),
            "summary": {
                "linked_rule_count": len(linked_rules),
                "template_name": clause.template_name,
                "category_path": " / ".join(
                    item for item in [clause.category_lv1, clause.category_lv2] if item
                ),
            },
            "document": document.model_dump() if document else None,
            "source_document_context": self._document_version_context(document) if document else None,
            "linked_rules": [rule.model_dump() for rule in linked_rules],
        }

    def rule_metadata(self, rule_id: str) -> dict | None:
        rule = self.rule_store.get(rule_id)
        if rule is None:
            return None
        source_document = self.document_store.get(rule.source_document_id) if rule.source_document_id else None
        source_clauses = []
        for clause_id in rule.basis_policy:
            clause = self.clause_store.get(clause_id)
            if clause is not None:
                source_clauses.append(
                    self._build_clause_summary(clause, document=source_document, content_chars=480)
                )
        return {
            "rule": rule.model_dump(),
            "summary": {
                "source_clause_count": len(source_clauses),
                "enabled": rule.enabled,
                "status": rule.status,
                "source_document_name": source_document.name if source_document else None,
            },
            "source_document": source_document.model_dump() if source_document else None,
            "source_document_context": self._document_version_context(source_document) if source_document else None,
            "source_clauses": source_clauses,
        }

    def patch_document(self, doc_id: str, **fields) -> DocumentRecord | None:
        document = self.document_store.get(doc_id)
        if document is None:
            return None
        updated = document.model_copy(update=fields)
        return self.document_store.save(updated)

    def page_image_path(self, doc_id: str, page: int) -> Path | None:
        document = self.document_store.get(doc_id)
        if document is None:
            return None
        source_path = Path(document.source_file)
        if not source_path.exists():
            return None
        target_dir = self.storage_root / "base" / doc_id / "pages"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"page_{page:03d}.png"
        if target_path.exists():
            return target_path
        if source_path.suffix.lower() != ".pdf":
            return None
        with fitz.open(source_path) as pdf:
            if page < 1 or page > pdf.page_count:
                return None
            pixmap = pdf.load_page(page - 1).get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            pixmap.save(target_path)
        return target_path

    def _persist_file(self, doc_id: str, file_name: str, file_bytes: bytes) -> Path:
        target_dir = self.storage_root / "base" / doc_id
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / file_name
        file_path.write_bytes(file_bytes)
        return file_path

    def _parse(self, file_path: Path) -> dict:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self.pdf_parser.parse(file_path)
        if suffix == ".docx":
            return self.docx_parser.parse(file_path)
        raise ValueError(f"Unsupported file type: {file_path.suffix}")

    def _generate_rule_drafts(self, document: DocumentRecord, clauses: list[ClauseRecord]) -> list[RuleRecord]:
        clause_by_keyword: dict[str, list[str]] = {}
        for clause in clauses:
            haystack = f"{clause.title}\n{clause.content}"
            for item in self.rule_catalog:
                if any(keyword in haystack for keyword in item["keywords"]):
                    clause_by_keyword.setdefault(item["id"], []).append(clause.id)
        rules: list[RuleRecord] = []
        for item in self.rule_catalog:
            basis_policy = clause_by_keyword.get(item["id"], [])
            if not basis_policy:
                continue
            rules.append(
                RuleRecord(
                    id=item["id"],
                    name=item["name"],
                    enabled=False,
                    rule_type=item["department"],
                    contract_categories=[],
                    severity=item["severity"],
                    basis_policy=basis_policy[:5],
                    logic=item["logic"],
                    suggestion_template=item["suggestion_template"],
                    department=item["department"],
                    source_document_id=document.id,
                    status="draft",
                )
            )
        return rules

    def _build_clause_summary(
        self,
        clause: ClauseRecord,
        *,
        document: DocumentRecord | None = None,
        content_chars: int = 240,
    ) -> dict:
        return {
            "id": clause.id,
            "document_id": clause.document_id,
            "doc_type": clause.doc_type,
            "template_id": clause.template_id,
            "template_name": clause.template_name,
            "category_lv1": clause.category_lv1,
            "category_lv2": clause.category_lv2,
            "clause_no": clause.clause_no,
            "title": clause.title,
            "clause_type": clause.clause_type,
            "content": clause.content[:content_chars],
            "page_start": clause.page_start,
            "page_end": clause.page_end,
            "status": clause.status,
            "effective_ts": clause.effective_ts,
            "abolish_ts": clause.abolish_ts,
            "risk_tags": clause.risk_tags,
            "preview": self._clause_preview(document or self.document_store.get(clause.document_id), clause),
        }

    @staticmethod
    def _build_clause_list_item(clause: ClauseRecord) -> dict:
        return {
            "id": clause.id,
            "document_id": clause.document_id,
            "doc_type": clause.doc_type,
            "template_id": clause.template_id,
            "template_name": clause.template_name,
            "category_lv1": clause.category_lv1,
            "category_lv2": clause.category_lv2,
            "clause_no": clause.clause_no,
            "title": clause.title,
            "clause_type": clause.clause_type,
            "content": clause.content[:220],
            "page_start": clause.page_start,
            "page_end": clause.page_end,
            "status": clause.status,
            "effective_ts": clause.effective_ts,
            "abolish_ts": clause.abolish_ts,
            "risk_tags": clause.risk_tags,
        }

    def _clause_preview(self, document: DocumentRecord | None, clause: ClauseRecord) -> dict | None:
        if document is None:
            return None
        image_path = self.page_image_path(document.id, clause.page_start)
        box_context = self._clause_box_context(document, clause)
        return {
            "page": clause.page_start,
            "image_url": f"/api/base/documents/{document.id}/pages/{clause.page_start}/image" if image_path else None,
            "excerpt": clause.content[:220],
            "boxes": box_context.get("boxes", []) if box_context else [],
            "page_width": box_context.get("page_width") if box_context else None,
            "page_height": box_context.get("page_height") if box_context else None,
        }

    def _clause_box_context(self, document: DocumentRecord, clause: ClauseRecord) -> dict | None:
        source_path = Path(document.source_file)
        if source_path.suffix.lower() != ".pdf" or not source_path.exists():
            return None
        try:
            with fitz.open(source_path) as pdf:
                page = pdf.load_page(max(0, clause.page_start - 1))
                boxes = []
                terms = [clause.title.strip(), (clause.content or "").strip().splitlines()[0][:40] if clause.content else ""]
                for term in terms:
                    if not term:
                        continue
                    for rect in page.search_for(term, quads=False)[:6]:
                        boxes.append(
                            {
                                "x0": round(rect.x0, 2),
                                "y0": round(rect.y0, 2),
                                "x1": round(rect.x1, 2),
                                "y1": round(rect.y1, 2),
                            }
                        )
                    if boxes:
                        break
                return {
                    "boxes": boxes[:6],
                    "page_width": round(page.rect.width, 2),
                    "page_height": round(page.rect.height, 2),
                }
        except Exception:
            return None

    @staticmethod
    def _dedupe_clauses(clauses: list[ClauseRecord]) -> list[ClauseRecord]:
        seen: set[tuple[str | None, str, int, int]] = set()
        items: list[ClauseRecord] = []
        for clause in clauses:
            key = (clause.template_id, clause.title, clause.page_start, clause.page_end)
            if key in seen:
                continue
            seen.add(key)
            items.append(clause)
        return items

    @staticmethod
    def _dedupe_rules(rules: list[RuleRecord]) -> list[RuleRecord]:
        seen: set[tuple[str, str]] = set()
        items: list[RuleRecord] = []
        for rule in rules:
            key = (rule.id, rule.source_document_id or "")
            if key in seen:
                continue
            seen.add(key)
            items.append(rule)
        return items

    @staticmethod
    def _dedupe_template_catalog(items: list[dict]) -> list[dict]:
        seen: set[tuple[str, int, int]] = set()
        catalog: list[dict] = []
        for item in items:
            key = (str(item.get("template_name") or item.get("template_id") or ""), int(item.get("start_page") or 1), int(item.get("end_page") or 1))
            if key in seen:
                continue
            seen.add(key)
            catalog.append(item)
        return catalog

    def _document_version_context(self, document: DocumentRecord | None) -> dict:
        if document is None:
            return {
                "same_series": [],
                "previous_versions": [],
                "next_version": None,
            }

        all_documents = self.document_store.list()
        same_series = [
            item
            for item in all_documents
            if item.name == document.name and item.doc_type == document.doc_type
        ]
        same_series.sort(key=lambda item: (item.effective_ts, item.created_at), reverse=True)

        previous_versions = [
            item
            for item in same_series
            if item.replaced_by == document.id
        ]
        next_version = next((item for item in all_documents if item.id == document.replaced_by), None)

        return {
            "same_series": [item.model_dump() for item in same_series],
            "previous_versions": [item.model_dump() for item in previous_versions],
            "next_version": next_version.model_dump() if next_version else None,
        }

    @staticmethod
    def _enrich_template_catalog(items: list[dict], clauses: list[ClauseRecord]) -> list[dict]:
        clause_map: dict[str, list[ClauseRecord]] = {}
        for clause in clauses:
            if clause.template_id:
                clause_map.setdefault(clause.template_id, []).append(clause)

        name_buckets: dict[str, list[dict]] = {}
        enriched: list[dict] = []
        for raw in items:
            item = dict(raw)
            template_id = str(item.get("template_id") or "")
            template_name = str(item.get("template_name") or "")
            template_clauses = sorted(
                clause_map.get(template_id, []),
                key=lambda current: (current.page_start, current.clause_no or "", current.title),
            )
            key_titles: list[str] = []
            for clause in template_clauses:
                title = (clause.title or "").strip()
                if title and title not in key_titles:
                    key_titles.append(title)
                if len(key_titles) >= 4:
                    break
            item["preview_page"] = item.get("start_page")
            item["clause_count"] = len(template_clauses)
            item["key_clause_titles"] = key_titles
            item["signature"] = " / ".join(key_titles[:3]) if key_titles else f"第 {item.get('start_page')}-{item.get('end_page')} 页"
            name_buckets.setdefault(template_name, []).append(item)
            enriched.append(item)

        for same_name_items in name_buckets.values():
            if len(same_name_items) <= 1:
                continue
            same_name_items.sort(key=lambda current: (int(current.get("start_page") or 1), int(current.get("end_page") or 1)))
            total = len(same_name_items)
            title_sets = [set(item.get("key_clause_titles") or []) for item in same_name_items]
            for index, item in enumerate(same_name_items, start=1):
                item["same_name_index"] = index
                item["same_name_total"] = total
                item["disambiguation_label"] = f"同名模板 {index}/{total} · 第 {item.get('start_page')}-{item.get('end_page')} 页"
                other_titles = set().union(*[titles for current_index, titles in enumerate(title_sets) if current_index != index - 1])
                current_titles = list(title_sets[index - 1])
                variant_cues = [title for title in current_titles if title and title not in other_titles][:3]
                if not variant_cues:
                    variant_cues = list(item.get("key_clause_titles") or [])[:2]
                item["auto_variant_cues"] = variant_cues
                item["auto_variant_summary"] = "自动区分依据：" + " / ".join(variant_cues) if variant_cues else None

        return enriched

    @staticmethod
    def _enrich_template_catalog(items: list[dict], clauses: list[ClauseRecord]) -> list[dict]:
        clause_map: dict[str, list[ClauseRecord]] = {}
        for clause in clauses:
            if clause.template_id:
                clause_map.setdefault(clause.template_id, []).append(clause)

        name_buckets: dict[str, list[dict]] = {}
        enriched: list[dict] = []
        for raw in items:
            item = dict(raw)
            template_id = str(item.get("template_id") or "")
            template_name = str(item.get("template_name") or "")
            template_clauses = sorted(
                clause_map.get(template_id, []),
                key=lambda current: (current.page_start, current.clause_no or "", current.title),
            )
            key_titles: list[str] = []
            for clause in template_clauses:
                title = (clause.title or "").strip()
                if title and title not in key_titles:
                    key_titles.append(title)
                if len(key_titles) >= 4:
                    break

            usage_profile, usage_profile_basis = KnowledgeBaseService._build_template_usage_profile(
                template_name=template_name,
                category_lv1=str(item.get("category_lv1") or ""),
                category_lv2=str(item.get("category_lv2") or ""),
                clauses=template_clauses,
            )

            item["preview_page"] = item.get("start_page")
            item["clause_count"] = len(template_clauses)
            item["key_clause_titles"] = key_titles
            item["signature"] = " / ".join(key_titles[:3]) if key_titles else f"第 {item.get('start_page')}-{item.get('end_page')} 页"
            item["usage_profile"] = usage_profile
            item["usage_profile_basis"] = usage_profile_basis
            item["usage_profile_summary"] = (
                f"{usage_profile}（依据：{' / '.join(usage_profile_basis[:3])}）"
                if usage_profile and usage_profile_basis
                else usage_profile
            )
            name_buckets.setdefault(template_name, []).append(item)
            enriched.append(item)

        for same_name_items in name_buckets.values():
            if len(same_name_items) <= 1:
                continue
            same_name_items.sort(key=lambda current: (int(current.get("start_page") or 1), int(current.get("end_page") or 1)))
            total = len(same_name_items)
            title_sets = [set(item.get("key_clause_titles") or []) for item in same_name_items]
            for index, item in enumerate(same_name_items, start=1):
                item["same_name_index"] = index
                item["same_name_total"] = total
                item["disambiguation_label"] = f"同名模板 {index}/{total} · 第 {item.get('start_page')}-{item.get('end_page')} 页"
                other_titles = set().union(
                    *[titles for current_index, titles in enumerate(title_sets) if current_index != index - 1]
                )
                current_titles = list(title_sets[index - 1])
                variant_cues = [title for title in current_titles if title and title not in other_titles][:3]
                if not variant_cues:
                    variant_cues = list(item.get("key_clause_titles") or [])[:2]
                item["auto_variant_cues"] = variant_cues
                item["auto_variant_summary"] = "自动区分依据：" + " / ".join(variant_cues) if variant_cues else None

        return enriched

    @staticmethod
    def _build_template_usage_profile(
        *,
        template_name: str,
        category_lv1: str,
        category_lv2: str,
        clauses: list[ClauseRecord],
    ) -> tuple[str | None, list[str]]:
        title_text = " ".join((clause.title or "").strip() for clause in clauses[:10])
        content_text = " ".join((clause.content or "").strip()[:180] for clause in clauses[:8])
        context_text = "\n".join(
            part
            for part in [template_name, category_lv1, category_lv2, title_text, content_text]
            if part
        )
        domain_text = "\n".join(part for part in [template_name, category_lv1, category_lv2] if part)

        def match_keywords(keywords: list[str]) -> list[str]:
            return [keyword for keyword in keywords if keyword in context_text][:4]

        if "仓储" in domain_text:
            occupancy_basis = match_keywords(["房屋", "移交日", "保证金", "物业", "场地", "承重", "退场", "装修"])
            service_basis = match_keywords(["仓储服务", "入库", "出库", "保管", "存货", "货物", "盘点", "装卸", "仓储费", "发票"])
            if len(occupancy_basis) >= max(2, len(service_basis)):
                return "场地占用型仓储合同", occupancy_basis
            if service_basis:
                return "标准仓储服务型合同", service_basis
            return "通用仓储合同模板", match_keywords(["仓储", "保管", "货物"]) or [template_name]

        if "技术服务" in domain_text:
            measurement_basis = match_keywords(["测量", "测绘", "点云", "激光雷达", "数据采集", "控制测量", "纵横断面", "勘测"])
            if measurement_basis:
                return "测量采集型技术服务模板", measurement_basis
            return "通用技术服务模板", match_keywords(["技术服务", "服务成果", "服务费"]) or [template_name]

        if "审计" in domain_text:
            audit_basis = match_keywords(["审计", "审计报告", "注册会计师", "被审计单位", "审计准则"])
            if audit_basis:
                return "审计鉴证服务型模板", audit_basis

        if "勘察" in domain_text or "设计" in domain_text:
            design_basis = match_keywords(["工程勘察", "勘察设计", "设计成果", "图纸", "勘察", "设计任务"])
            if design_basis:
                return "工程勘察设计型模板", design_basis

        if "检测" in domain_text or "检验" in domain_text:
            lab_basis = match_keywords(["检测", "检验", "试验", "样品", "检测报告"])
            if lab_basis:
                return "检测检验服务型模板", lab_basis

        if "法律" in domain_text or "律师" in domain_text:
            legal_basis = match_keywords(["法律服务", "律师", "法律意见", "代理", "诉讼", "仲裁"])
            if legal_basis:
                return "法律服务型模板", legal_basis

        fallback_basis = [title for title in [(clause.title or "").strip() for clause in clauses[:4]] if title][:3]
        if "仓储合同" in template_name:
            return "通用仓储合同模板", fallback_basis
        if "技术服务合同" in template_name:
            return "通用技术服务模板", fallback_basis
        if "合同" in template_name:
            return "通用合同模板", fallback_basis
        return None, fallback_basis
