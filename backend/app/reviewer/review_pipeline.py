from __future__ import annotations

from datetime import datetime
from typing import Callable

from app.classifier.contract_classifier import ContractClassifier
from app.comparator.template_comparator import TemplateComparator
from app.extractor.contract_schema_extractor import ContractSchemaExtractor
from app.redis_store.report_store import ReportStore
from app.redis_store.rule_store import RuleStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.policy_retriever import PolicyRetriever
from app.retrieval.template_retriever import TemplateRetriever
from app.reviewer.issue_generator import IssueGenerator
from app.reviewer.report_generator import ReportGenerator
from app.rule_engine.rule_runner import RuleRunner
from app.schemas.contract import KnowledgeBaseReviewState, KnowledgeBaseReviewStep
from app.schemas.review import ReviewRequest
from app.storage.local_store import LocalStore


class ReviewPipeline:
    def __init__(
        self,
        *,
        local_store: LocalStore,
        report_store: ReportStore,
        rule_store: RuleStore,
        classifier: ContractClassifier,
        schema_extractor: ContractSchemaExtractor,
        template_retriever: TemplateRetriever,
        comparator: TemplateComparator,
        policy_retriever: PolicyRetriever,
        hybrid_retriever: HybridRetriever,
        rule_runner: RuleRunner,
        issue_generator: IssueGenerator,
        report_generator: ReportGenerator,
    ) -> None:
        self.local_store = local_store
        self.report_store = report_store
        self.rule_store = rule_store
        self.classifier = classifier
        self.schema_extractor = schema_extractor
        self.template_retriever = template_retriever
        self.comparator = comparator
        self.policy_retriever = policy_retriever
        self.hybrid_retriever = hybrid_retriever
        self.rule_runner = rule_runner
        self.issue_generator = issue_generator
        self.report_generator = report_generator

    @staticmethod
    def _build_review_state(
        *,
        current_step_id: str,
        current_step_label: str,
        progress_percent: int,
        message: str,
        step_status_map: dict[str, str],
        detected_category: str | None = None,
        matched_template: dict | None = None,
        issue_count: int | None = None,
        status: str = "running",
    ) -> KnowledgeBaseReviewState:
        steps = [
            KnowledgeBaseReviewStep(id="classify_contract", label="识别合同类别", status=step_status_map.get("classify_contract", "pending")),
            KnowledgeBaseReviewStep(id="match_template", label="匹配有效范本", status=step_status_map.get("match_template", "pending")),
            KnowledgeBaseReviewStep(id="extract_schema", label="抽取结构化字段", status=step_status_map.get("extract_schema", "pending")),
            KnowledgeBaseReviewStep(id="compare_template", label="比对范本条款", status=step_status_map.get("compare_template", "pending")),
            KnowledgeBaseReviewStep(id="retrieve_policy", label="检索制度依据", status=step_status_map.get("retrieve_policy", "pending")),
            KnowledgeBaseReviewStep(id="run_rules", label="执行规则校验", status=step_status_map.get("run_rules", "pending")),
            KnowledgeBaseReviewStep(id="generate_issues", label="生成审查问题", status=step_status_map.get("generate_issues", "pending")),
            KnowledgeBaseReviewStep(id="save_report", label="写入审查报告", status=step_status_map.get("save_report", "pending")),
        ]
        return KnowledgeBaseReviewState(
            status=status,
            progressPercent=progress_percent,
            currentStepId=current_step_id,
            currentStepLabel=current_step_label,
            message=message,
            detectedCategory=detected_category,
            matchedTemplateId=matched_template.get("template_id") if matched_template else None,
            matchedTemplateName=matched_template.get("template_name") if matched_template else None,
            issueCount=issue_count,
            steps=steps,
        )

    @staticmethod
    def _build_template_message(
        *,
        detected_category: str,
        matched_template: dict | None,
        selected_template_id: str | None,
    ) -> str:
        if matched_template is None:
            return f"已识别合同类别为“{detected_category}”，但当前有效范本库中未找到匹配范本，将继续执行制度与规则校验。"

        template_name = matched_template.get("template_name") or "未命名范本"
        template_category = matched_template.get("category_lv1") or matched_template.get("category_lv2") or ""
        if selected_template_id and template_category and detected_category not in {template_category, matched_template.get("category_lv2")}:
            return (
                f"已识别合同类别为“{detected_category}”，但所选范本“{template_name}”"
                f"属于“{template_category}”，与当前合同类型不完全一致，建议人工复核。"
            )
        return f"已按“{detected_category}”匹配有效范本：{template_name}。"

    async def review_contract(
        self,
        request: ReviewRequest,
        progress_callback: Callable[[KnowledgeBaseReviewState], None] | None = None,
    ) -> dict:
        source_record = self.local_store.get_task(request.source_task_id)
        if source_record.result is None:
            raise ValueError("Source contract result not generated")

        today = int(datetime.now().strftime("%Y%m%d"))
        step_status_map = {
            "classify_contract": "running",
            "match_template": "pending",
            "extract_schema": "pending",
            "compare_template": "pending",
            "retrieve_policy": "pending",
            "run_rules": "pending",
            "generate_issues": "pending",
            "save_report": "pending",
        }

        def emit(
            step_id: str,
            label: str,
            progress: int,
            message: str,
            *,
            status: str = "running",
            detected_category: str | None = None,
            matched_template: dict | None = None,
            issue_count: int | None = None,
        ) -> None:
            if status == "failed":
                step_status_map[step_id] = "failed"
            else:
                for key, current in list(step_status_map.items()):
                    if key == step_id:
                        step_status_map[key] = "running" if status == "running" else "completed"
                    elif current == "running":
                        step_status_map[key] = "completed"
            if progress_callback is not None:
                progress_callback(
                    self._build_review_state(
                        current_step_id=step_id,
                        current_step_label=label,
                        progress_percent=progress,
                        message=message,
                        step_status_map=step_status_map,
                        detected_category=detected_category,
                        matched_template=matched_template,
                        issue_count=issue_count,
                        status=status,
                    )
                )

        emit("classify_contract", "识别合同类别", 12, "正在识别合同类别。")
        detected_category = await self.classifier.classify(source_record.result)
        emit("match_template", "匹配有效范本", 24, f"已识别合同类别：{detected_category}。", detected_category=detected_category)

        contract_schema = self.schema_extractor.extract(request.source_task_id, detected_category, source_record.result)
        emit("extract_schema", "抽取结构化字段", 38, "正在抽取合同主体、价款、付款、期限等关键字段。", detected_category=detected_category)

        matched_template = await self.template_retriever.match_template(
            contract_schema,
            selected_template_id=request.selected_template_id,
            today=today,
        )
        emit(
            "compare_template",
            "比对范本条款",
            52,
            self._build_template_message(
                detected_category=detected_category,
                matched_template=matched_template,
                selected_template_id=request.selected_template_id,
            ),
            detected_category=detected_category,
            matched_template=matched_template,
        )

        contract_schema = contract_schema.model_copy(
            update={
                "matched_template_id": matched_template.get("template_id") if matched_template else None,
                "matched_template_name": matched_template.get("template_name") if matched_template else None,
            }
        )
        self.report_store.save_schema(contract_schema)

        comparison = self.comparator.compare(
            source_record.result.clauses,
            matched_template.get("clauses", []) if matched_template else [],
        )
        emit(
            "retrieve_policy",
            "检索制度依据",
            66,
            "正在根据差异条款和关键字段检索制度依据。",
            detected_category=detected_category,
            matched_template=matched_template,
        )

        enabled_rules = [rule for rule in self.rule_store.list() if rule.enabled]
        emit(
            "run_rules",
            "执行规则校验",
            78,
            f"正在执行 {len(enabled_rules)} 条已启用规则。",
            detected_category=detected_category,
            matched_template=matched_template,
        )
        rule_hits = self.rule_runner.run(
            contract_schema=contract_schema,
            matched_template=matched_template,
            comparison=comparison,
            rules=enabled_rules,
        )

        policy_lookup_cache: dict[tuple[str, tuple[str, ...], bool], list[str] | list[dict]] = {}
        policy_clause_pool = [
            clause
            for clause in self.policy_retriever.clause_store.list(doc_type="policy", include_embedding=False)
            if clause.status in {"effective", "partially_effective"}
            and clause.effective_ts <= today <= clause.abolish_ts
        ]
        policy_clause_map = {clause.id: clause for clause in policy_clause_pool}

        def search_policy_pool(query: str, top_k: int = 3):
            normalized_terms = [item for item in query.replace("，", " ").replace("。", " ").replace("/", " ").split() if item]
            scored: list[tuple[float, object]] = []
            for clause in policy_clause_pool:
                haystack = f"{clause.title}\n{clause.content}"
                score = 0.0
                if query and query in haystack:
                    score += 5.0
                for term in normalized_terms:
                    if term in haystack:
                        score += 1.0
                if score <= 0 and query:
                    overlap = len({char for char in query if char.strip() and char in haystack})
                    if overlap >= 2:
                        score += overlap / max(len(query), 1)
                if score > 0:
                    scored.append((score, clause))
            scored.sort(key=lambda item: item[0], reverse=True)
            return [item[1] for item in scored[:top_k]]

        def policy_lookup(
            query: str,
            clause_ids: list[str] | None = None,
            return_details: bool = False,
        ):
            cache_key = (query, tuple(clause_ids or []), return_details)
            if cache_key in policy_lookup_cache:
                return policy_lookup_cache[cache_key]
            clauses = []
            if clause_ids:
                clauses = [policy_clause_map.get(clause_id) for clause_id in clause_ids]
                clauses = [item for item in clauses if item is not None]
            if not clauses:
                clauses = search_policy_pool(query, top_k=3)
            if return_details:
                details = [
                    {
                        "id": clause.id,
                        "title": clause.title,
                        "content": clause.content[:240],
                        "page_start": clause.page_start,
                        "page_end": clause.page_end,
                        "document_id": clause.document_id,
                    }
                    for clause in clauses
                ]
                policy_lookup_cache[cache_key] = details
                return details
            clause_id_list = [clause.id for clause in clauses]
            policy_lookup_cache[cache_key] = clause_id_list
            return clause_id_list

        def template_detail_builder(current_template: dict | None, clause_title: str) -> dict | None:
            if current_template is None:
                return None
            matched_clause = next(
                (item for item in current_template.get("clauses", []) if clause_title in item.title or item.title in clause_title),
                current_template.get("clauses", [None])[0] if current_template.get("clauses") else None,
            )
            return {
                "template_id": current_template.get("template_id"),
                "template_name": current_template.get("template_name"),
                "category_lv1": current_template.get("category_lv1"),
                "category_lv2": current_template.get("category_lv2"),
                "matched_clause_title": getattr(matched_clause, "title", None),
                "matched_clause_page": getattr(matched_clause, "page_start", None),
            }

        emit(
            "generate_issues",
            "生成审查问题",
            88,
            "规则校验已完成，正在生成审查问题与依据。",
            detected_category=detected_category,
            matched_template=matched_template,
        )
        issues = self.issue_generator.generate(
            comparison=comparison,
            rule_hits=rule_hits,
            matched_template=matched_template,
            contract_schema=contract_schema,
            policy_lookup=policy_lookup,
            template_detail_builder=template_detail_builder,
        )

        emit(
            "save_report",
            "写入审查报告",
            96,
            f"已生成 {len(issues)} 个制度校验问题，正在写入报告。",
            detected_category=detected_category,
            matched_template=matched_template,
            issue_count=len(issues),
        )
        report = self.report_generator.generate(
            contract_id=contract_schema.contract_id,
            detected_category=detected_category,
            matched_template=matched_template,
            issues=issues,
        )
        self.report_store.save_report(report)
        emit(
            "save_report",
            "写入审查报告",
            100,
            report.summary,
            status="completed",
            detected_category=detected_category,
            matched_template=matched_template,
            issue_count=len(issues),
        )

        return {
            "contract_schema": contract_schema,
            "matched_template": matched_template,
            "comparison": comparison,
            "report": report,
            "policy_suggestions": await self.hybrid_retriever.search(detected_category, today=today, top_k=5),
        }
