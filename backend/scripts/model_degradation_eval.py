from __future__ import annotations

import argparse
import asyncio
import ast
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.audit_focus_agent import AuditFocusAgent
from app.agents.contract_agent import ContractAgent
from app.agents.contract_parser_agent import ContractParserAgent
from app.agents.planner import Planner
from app.agents.verification_agent import VerificationAgent
from app.classifier.contract_classifier import ContractClassifier
from app.comparator.template_comparator import TemplateComparator
from app.config import Settings
from app.embedding.embedding_client import EmbeddingClient
from app.extractor.contract_schema_extractor import ContractSchemaExtractor
from app.llm.llm_client import LLMClient
from app.redis_store.clause_store import ClauseStore
from app.redis_store.document_store import DocumentStore
from app.redis_store.redis_client import RedisClientFactory
from app.redis_store.report_store import ReportStore
from app.redis_store.review_task_store import ReviewTaskStore
from app.redis_store.rule_store import RuleStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.policy_retriever import PolicyRetriever
from app.retrieval.template_retriever import TemplateRetriever
from app.reviewer.issue_generator import IssueGenerator
from app.reviewer.report_generator import ReportGenerator
from app.reviewer.review_pipeline import ReviewPipeline
from app.rule_engine.rule_runner import RuleRunner
from app.schemas.review import ReviewRequest
from app.services.confidence_service import ConfidenceService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.ocr_service import OCRService
from app.services.paddle_ocr_service import PaddleOCRService
from app.services.qwen_service import QwenService
from app.storage.local_store import LocalStore
from app.tools.rule_engine_adapter import RuleEngineAdapter


@dataclass
class ModelProfile:
    name: str
    qwen_api_key: str
    qwen_base_url: str
    qwen_model_name: str
    qwen_vision_model_name: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    min_timeout_seconds: int = 0
    qwen_parallel_requests: int | None = None
    key_fact_batch_size: int | None = None


@dataclass
class EvalInput:
    label: str
    use_builtin_example: bool
    file_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline vs local-model degradation evaluation.")
    parser.add_argument("--label", default="builtin-example", help="Input label shown in the report.")
    parser.add_argument("--use-builtin-example", action="store_true", help="Run with built-in sample contract.")
    parser.add_argument("--file", type=str, default="", help="Absolute path to a real contract file.")
    parser.add_argument("--baseline-name", default="baseline-full-model", help="Baseline profile name.")
    parser.add_argument("--candidate-name", default="local-9b", help="Candidate profile name.")
    parser.add_argument("--candidate-base-url", required=True, help="Candidate OpenAI-compatible base URL.")
    parser.add_argument("--candidate-api-key", required=True, help="Candidate API key.")
    parser.add_argument("--candidate-model", required=True, help="Candidate chat model id.")
    parser.add_argument(
        "--candidate-vision-model",
        default="",
        help="Optional candidate vision model. Defaults to the candidate chat model.",
    )
    parser.add_argument(
        "--candidate-llm-model",
        default="",
        help="Optional candidate LLM model for app.llm.LLMClient. Defaults to the candidate chat model.",
    )
    parser.add_argument(
        "--candidate-embedding-base-url",
        default="",
        help="Optional embedding endpoint. Leave empty to keep baseline embedding config.",
    )
    parser.add_argument(
        "--candidate-embedding-api-key",
        default="",
        help="Optional embedding API key.",
    )
    parser.add_argument(
        "--candidate-embedding-model",
        default="",
        help="Optional embedding model id.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory. Defaults to output/evals/<timestamp>_<label>.",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    lowered = (value or "").strip().lower()
    return re.sub(r"\s+", "", lowered)


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "eval"


def build_input(args: argparse.Namespace) -> EvalInput:
    if args.use_builtin_example:
        return EvalInput(label=args.label, use_builtin_example=True, file_path=None)
    if not args.file:
        raise SystemExit("Either --use-builtin-example or --file must be provided.")
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")
    return EvalInput(label=args.label, use_builtin_example=False, file_path=file_path)


def build_output_dir(args: argparse.Namespace, input_spec: EvalInput) -> Path:
    if args.output_dir:
        return Path(args.output_dir).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = sanitize_filename(input_spec.label)
    return (PROJECT_ROOT / "output" / "evals" / f"{stamp}_{label}").resolve()


def build_baseline_profile(settings: Settings, name: str) -> ModelProfile:
    return ModelProfile(
        name=name,
        qwen_api_key=settings.qwen_api_key,
        qwen_base_url=settings.qwen_base_url,
        qwen_model_name=settings.qwen_model_name,
        qwen_vision_model_name=settings.qwen_vision_model_name,
        llm_api_key=settings.llm_api_key,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        embedding_api_key=settings.embedding_api_key,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
        min_timeout_seconds=0,
        qwen_parallel_requests=settings.qwen_parallel_requests,
        key_fact_batch_size=settings.key_fact_batch_size,
    )


def build_candidate_profile(settings: Settings, args: argparse.Namespace) -> ModelProfile:
    candidate_model = args.candidate_model
    return ModelProfile(
        name=args.candidate_name,
        qwen_api_key=args.candidate_api_key,
        qwen_base_url=args.candidate_base_url,
        qwen_model_name=candidate_model,
        qwen_vision_model_name=args.candidate_vision_model or candidate_model,
        llm_api_key=args.candidate_api_key,
        llm_base_url=args.candidate_base_url,
        llm_model=args.candidate_llm_model or candidate_model,
        embedding_api_key=args.candidate_embedding_api_key or settings.embedding_api_key,
        embedding_base_url=args.candidate_embedding_base_url or settings.embedding_base_url,
        embedding_model=args.candidate_embedding_model or settings.embedding_model,
        min_timeout_seconds=300,
        qwen_parallel_requests=1,
        key_fact_batch_size=2,
    )


def build_settings(base_settings: Settings, profile: ModelProfile, storage_dir: Path) -> Settings:
    return base_settings.model_copy(
        update={
            "qwen_api_key": profile.qwen_api_key,
            "qwen_base_url": profile.qwen_base_url,
            "qwen_model_name": profile.qwen_model_name,
            "qwen_vision_model_name": profile.qwen_vision_model_name,
            "llm_api_key": profile.llm_api_key,
            "llm_base_url": profile.llm_base_url,
            "llm_model": profile.llm_model,
            "embedding_api_key": profile.embedding_api_key,
            "embedding_base_url": profile.embedding_base_url,
            "embedding_model": profile.embedding_model,
            "qwen_cache_enabled": False,
            "ocr_cache_enabled": False,
            "qwen_parallel_requests": profile.qwen_parallel_requests or base_settings.qwen_parallel_requests,
            "key_fact_batch_size": profile.key_fact_batch_size or base_settings.key_fact_batch_size,
            "storage_dir": str(storage_dir),
        }
    )


def summarize_profile(profile: ModelProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "qwen_base_url": profile.qwen_base_url,
        "qwen_model_name": profile.qwen_model_name,
        "qwen_vision_model_name": profile.qwen_vision_model_name,
        "llm_base_url": profile.llm_base_url,
        "llm_model": profile.llm_model,
        "embedding_base_url": profile.embedding_base_url,
        "embedding_model": profile.embedding_model,
    }


def ensure_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class EvalQwenService(QwenService):
    def __init__(self, settings: Settings, *, min_timeout_seconds: int = 0) -> None:
        super().__init__(settings)
        self.min_timeout_seconds = max(0, int(min_timeout_seconds))

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        timeout: int = 60,
    ) -> dict[str, Any]:
        if not self.is_available:
            raise RuntimeError("Qwen API key is not configured.")

        payload = {
            "model": self.settings.qwen_model_name,
            "messages": [
                {
                    "role": "system",
                    "content": f"{system_prompt}\nReturn only one valid JSON object.",
                },
                {
                    "role": "user",
                    "content": f"{user_prompt}\nOutput JSON only.",
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        data = await self._post_chat(payload=payload, timeout=max(timeout, self.min_timeout_seconds))
        content = self._extract_content(data)
        repaired = self._repair_json_with_fallback(content)
        self._validate_schema(instance=repaired, schema=schema, label="Eval Qwen JSON")
        return repaired

    async def vision_json(
        self,
        prompt: str,
        image_path: Path,
        schema: dict[str, Any],
        timeout: int = 120,
    ) -> dict[str, Any]:
        return await super().vision_json(
            prompt=prompt,
            image_path=image_path,
            schema=schema,
            timeout=max(timeout, self.min_timeout_seconds),
        )

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise RuntimeError("Model response does not contain choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            joined = "".join(item.get("text", "") for item in content if isinstance(item, dict))
            if joined.strip():
                return joined
        if isinstance(content, str) and content.strip():
            return content
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        provider_specific = message.get("provider_specific_fields") or {}
        for key in ("reasoning_content", "reasoning"):
            value = provider_specific.get(key)
            if isinstance(value, str) and value.strip():
                return value
        raise RuntimeError("Model response did not include usable content or reasoning_content.")

    @classmethod
    def _repair_json_with_fallback(cls, raw_text: str) -> dict[str, Any]:
        try:
            return cls._repair_json(raw_text)
        except Exception:
            candidate = str(raw_text or "").strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```(?:json)?", "", candidate).strip()
                candidate = re.sub(r"```$", "", candidate).strip()
            for index, char in enumerate(candidate):
                if char != "{":
                    continue
                end = candidate.rfind("}")
                if end <= index:
                    continue
                snippet = candidate[index : end + 1]
                try:
                    parsed = ast.literal_eval(snippet)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    return json.loads(json.dumps(parsed, ensure_ascii=False))
            raise


def build_runtime(settings: Settings, profile: ModelProfile) -> tuple[LocalStore, ContractAgent, ReviewPipeline]:
    store = LocalStore(base_dir=Path(settings.storage_dir).resolve())
    qwen_service = EvalQwenService(settings, min_timeout_seconds=profile.min_timeout_seconds)
    document_service = DocumentService()
    paddle_ocr_service = PaddleOCRService(
        python_executable=settings.paddle_python_executable,
        timeout_seconds=settings.paddle_ocr_timeout_seconds,
        batch_size=settings.paddle_ocr_batch_size,
    )
    ocr_service = OCRService(
        settings=settings,
        qwen_service=qwen_service,
        paddle_ocr_service=paddle_ocr_service,
    )
    evidence_service = EvidenceService(qwen_service=qwen_service, settings=settings)
    confidence_service = ConfidenceService()
    planner = Planner()
    parser_agent = ContractParserAgent(qwen_service=qwen_service, settings=settings)
    audit_focus_agent = AuditFocusAgent(qwen_service=qwen_service)
    verification_agent = VerificationAgent(qwen_service=qwen_service)
    rule_engine_adapter = RuleEngineAdapter(settings=settings)

    redis_factory = RedisClientFactory(settings)
    redis_client = redis_factory.get_client()
    embedding_client = EmbeddingClient(settings)
    llm_client = LLMClient(settings)
    document_store = DocumentStore(redis_client)
    rule_store = RuleStore(redis_client)
    report_store = ReportStore(redis_client)
    ReviewTaskStore(redis_client)
    clause_store = ClauseStore(redis_client, embedding_client)
    policy_retriever = PolicyRetriever(clause_store)
    hybrid_retriever = HybridRetriever(clause_store)
    template_retriever = TemplateRetriever(clause_store, qwen_service=qwen_service)
    contract_classifier = ContractClassifier(qwen_service=qwen_service)
    schema_extractor = ContractSchemaExtractor()
    template_comparator = TemplateComparator()
    issue_generator = IssueGenerator()
    report_generator = ReportGenerator()
    rule_runner = RuleRunner()

    contract_agent = ContractAgent(
        document_service=document_service,
        ocr_service=ocr_service,
        parser_agent=parser_agent,
        audit_focus_agent=audit_focus_agent,
        verification_agent=verification_agent,
        evidence_service=evidence_service,
        confidence_service=confidence_service,
        planner=planner,
        storage_dir=Path(settings.storage_dir).resolve(),
        rule_engine_adapter=rule_engine_adapter,
    )
    review_pipeline = ReviewPipeline(
        local_store=store,
        report_store=report_store,
        rule_store=rule_store,
        classifier=contract_classifier,
        schema_extractor=schema_extractor,
        template_retriever=template_retriever,
        comparator=template_comparator,
        policy_retriever=policy_retriever,
        hybrid_retriever=hybrid_retriever,
        rule_runner=rule_runner,
        issue_generator=issue_generator,
        report_generator=report_generator,
    )
    _ = llm_client, document_store
    return store, contract_agent, review_pipeline


def summarize_run(
    *,
    profile: ModelProfile,
    input_spec: EvalInput,
    result: Any,
    audit_focuses: list[Any],
    verification_items: list[Any],
    review_result: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    kb = result.task.knowledgeBaseReview
    report = review_result["report"]
    issues = report.issues
    return {
        "profile": summarize_profile(profile),
        "input": {
            "label": input_spec.label,
            "use_builtin_example": input_spec.use_builtin_example,
            "file_path": str(input_spec.file_path) if input_spec.file_path else None,
        },
        "task_id": task_id,
        "contract_analysis": {
            "status": result.task.status,
            "elapsed_ms": result.task.elapsedMs,
            "page_count": len(result.pages),
            "section_count": len(result.sections),
            "clause_count": len(result.clauses),
            "key_fact_count": len(result.keyFacts),
            "audit_focus_count": len(audit_focuses),
            "verification_item_count": len(verification_items),
            "warnings": result.task.confidenceOverview.warnings,
            "overall_confidence": result.task.confidenceOverview.overall,
            "sections_confidence": result.task.confidenceOverview.sections,
            "clauses_confidence": result.task.confidenceOverview.clauses,
            "audit_confidence": result.task.confidenceOverview.audit,
        },
        "knowledge_base_review": {
            "status": kb.status if kb else None,
            "detected_category": report.detected_category,
            "matched_template_id": report.matched_template.get("template_id") if report.matched_template else None,
            "matched_template_name": report.matched_template.get("template_name") if report.matched_template else None,
            "issue_count": len(issues),
            "severity_distribution": dict(Counter(issue.severity for issue in issues)),
        },
    }


async def run_profile(
    *,
    base_settings: Settings,
    profile: ModelProfile,
    input_spec: EvalInput,
    output_dir: Path,
) -> dict[str, Any]:
    run_root = output_dir / sanitize_filename(profile.name)
    started = perf_counter()
    try:
        storage_dir = run_root / "storage"
        settings = build_settings(base_settings, profile, storage_dir)
        store, contract_agent, review_pipeline = build_runtime(settings, profile)

        file_name = input_spec.file_path.name if input_spec.file_path else "example_contract.pdf"
        record = store.create_task(
            file_name=file_name,
            model_name=settings.qwen_model_name,
            use_builtin_example=input_spec.use_builtin_example,
            file_path=input_spec.file_path,
        )
        artifacts = await contract_agent.analyze(
            task=record.task,
            relations=store.list_relations(),
            use_builtin_example=input_spec.use_builtin_example,
            file_path=input_spec.file_path,
        )
        store.save_result(
            task_id=record.task.taskId,
            result=artifacts.result,
            audit_focuses=artifacts.audit_focuses,
            verification_items=artifacts.verification_items,
            agent_steps=artifacts.agent_steps,
        )
        review_result = await review_pipeline.review_contract(ReviewRequest(source_task_id=record.task.taskId))
        report = review_result["report"]

        ensure_json(run_root / "contract_result.json", artifacts.result.model_dump(mode="json"))
        ensure_json(run_root / "audit_focuses.json", [item.model_dump(mode="json") for item in artifacts.audit_focuses])
        ensure_json(
            run_root / "verification_items.json",
            [item.model_dump(mode="json") for item in artifacts.verification_items],
        )
        ensure_json(run_root / "review_report.json", report.model_dump(mode="json"))
        ensure_json(
            run_root / "review_contract_schema.json",
            review_result["contract_schema"].model_dump(mode="json"),
        )

        summary = summarize_run(
            profile=profile,
            input_spec=input_spec,
            result=artifacts.result,
            audit_focuses=artifacts.audit_focuses,
            verification_items=artifacts.verification_items,
            review_result=review_result,
            task_id=record.task.taskId,
        )
        ensure_json(run_root / "summary.json", summary)
        return {
            "failed": False,
            "summary": summary,
            "result": artifacts.result.model_dump(mode="json"),
            "audit_focuses": [item.model_dump(mode="json") for item in artifacts.audit_focuses],
            "verification_items": [item.model_dump(mode="json") for item in artifacts.verification_items],
            "review_report": report.model_dump(mode="json"),
            "review_contract_schema": review_result["contract_schema"].model_dump(mode="json"),
            "paths": {
                "run_root": str(run_root),
                "contract_result": str(run_root / "contract_result.json"),
                "review_report": str(run_root / "review_report.json"),
                "summary": str(run_root / "summary.json"),
            },
        }
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        summary = {
            "profile": summarize_profile(profile),
            "input": {
                "label": input_spec.label,
                "use_builtin_example": input_spec.use_builtin_example,
                "file_path": str(input_spec.file_path) if input_spec.file_path else None,
            },
            "task_id": None,
            "error": str(exc),
            "contract_analysis": {
                "status": "failed",
                "elapsed_ms": elapsed_ms,
                "page_count": None,
                "section_count": None,
                "clause_count": None,
                "key_fact_count": None,
                "audit_focus_count": None,
                "verification_item_count": None,
                "warnings": None,
                "overall_confidence": None,
                "sections_confidence": None,
                "clauses_confidence": None,
                "audit_confidence": None,
            },
            "knowledge_base_review": {
                "status": "not_run",
                "detected_category": None,
                "matched_template_id": None,
                "matched_template_name": None,
                "issue_count": None,
                "severity_distribution": {},
            },
        }
        ensure_json(run_root / "summary.json", summary)
        ensure_json(run_root / "error.json", {"error": str(exc), "elapsed_ms": elapsed_ms})
        return {
            "failed": True,
            "error": str(exc),
            "summary": summary,
            "result": None,
            "audit_focuses": [],
            "verification_items": [],
            "review_report": None,
            "review_contract_schema": None,
            "paths": {
                "run_root": str(run_root),
                "summary": str(run_root / "summary.json"),
                "error": str(run_root / "error.json"),
            },
        }


def pairwise_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def compare_lists_exact(baseline: list[str], candidate: list[str]) -> dict[str, Any]:
    baseline_map = {normalize_text(item): item for item in baseline if normalize_text(item)}
    candidate_map = {normalize_text(item): item for item in candidate if normalize_text(item)}
    overlap_keys = sorted(set(baseline_map) & set(candidate_map))
    baseline_only = [baseline_map[key] for key in baseline_map.keys() - candidate_map.keys()]
    candidate_only = [candidate_map[key] for key in candidate_map.keys() - baseline_map.keys()]
    return {
        "baseline_count": len(baseline),
        "candidate_count": len(candidate),
        "overlap_count": len(overlap_keys),
        "overlap_ratio_vs_baseline": round(len(overlap_keys) / max(len(baseline_map), 1), 4),
        "overlap_ratio_vs_candidate": round(len(overlap_keys) / max(len(candidate_map), 1), 4),
        "baseline_only_sample": baseline_only[:10],
        "candidate_only_sample": candidate_only[:10],
    }


def compare_key_facts(baseline_result: dict[str, Any], candidate_result: dict[str, Any]) -> dict[str, Any]:
    baseline_facts = baseline_result["keyFacts"]
    candidate_facts = candidate_result["keyFacts"]
    baseline_by_label = {normalize_text(item["label"]): item for item in baseline_facts if normalize_text(item["label"])}
    candidate_by_label = {normalize_text(item["label"]): item for item in candidate_facts if normalize_text(item["label"])}
    shared_labels = sorted(set(baseline_by_label) & set(candidate_by_label))
    value_scores = []
    mismatches = []
    for label in shared_labels:
        base_item = baseline_by_label[label]
        cand_item = candidate_by_label[label]
        score = pairwise_similarity(str(base_item.get("value", "")), str(cand_item.get("value", "")))
        value_scores.append(score)
        if score < 0.85:
            mismatches.append(
                {
                    "label": base_item.get("label"),
                    "baseline_value": base_item.get("value"),
                    "candidate_value": cand_item.get("value"),
                    "similarity": round(score, 4),
                }
            )
    return {
        "label_overlap": compare_lists_exact(
            [item["label"] for item in baseline_facts],
            [item["label"] for item in candidate_facts],
        ),
        "value_similarity_avg": round(sum(value_scores) / max(len(value_scores), 1), 4),
        "value_mismatch_sample": mismatches[:10],
    }


def compare_issue_sets(baseline_report: dict[str, Any], candidate_report: dict[str, Any]) -> dict[str, Any]:
    baseline_issues = baseline_report["issues"]
    candidate_issues = candidate_report["issues"]
    return {
        "problem_overlap": compare_lists_exact(
            [item["problem"] for item in baseline_issues],
            [item["problem"] for item in candidate_issues],
        ),
        "clause_location_overlap": compare_lists_exact(
            [item["clause_location"] for item in baseline_issues],
            [item["clause_location"] for item in candidate_issues],
        ),
        "severity_distribution_baseline": dict(Counter(item["severity"] for item in baseline_issues)),
        "severity_distribution_candidate": dict(Counter(item["severity"] for item in candidate_issues)),
    }


def build_assessment(baseline: dict[str, Any], candidate: dict[str, Any], comparison: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    base_analysis = baseline["summary"]["contract_analysis"]
    cand_analysis = candidate["summary"]["contract_analysis"]
    base_kb = baseline["summary"]["knowledge_base_review"]
    cand_kb = candidate["summary"]["knowledge_base_review"]

    if cand_kb["detected_category"] != base_kb["detected_category"]:
        notes.append(
            f"制度审查分类发生漂移：基线是 {base_kb['detected_category']}，候选是 {cand_kb['detected_category']}。"
        )
    if cand_kb["matched_template_id"] != base_kb["matched_template_id"]:
        notes.append(
            "制度审查匹配到的范本发生变化，这通常意味着后续问题清单会整体偏移。"
        )
    clause_overlap = comparison["contract_analysis"]["clause_title_overlap"]["overlap_ratio_vs_baseline"]
    if clause_overlap < 0.8:
        notes.append(f"条款抽取重合度较低，候选模型对主工作台结构化结果的保持度不足（{clause_overlap:.0%}）。")
    fact_similarity = comparison["contract_analysis"]["key_fact_comparison"]["value_similarity_avg"]
    if fact_similarity < 0.85:
        notes.append(f"关键事实值相似度偏低（{fact_similarity:.0%}），后续规则命中和审查建议会被连带放大。")
    issue_overlap = comparison["knowledge_base_review"]["problem_overlap"]["overlap_ratio_vs_baseline"]
    if issue_overlap < 0.6:
        notes.append(f"制度问题清单与基线重合度偏低（{issue_overlap:.0%}），需要重点看是召回下降还是模板漂移导致。")
    delta_issues = cand_kb["issue_count"] - base_kb["issue_count"]
    if delta_issues <= -5:
        notes.append(f"候选模型比基线少报 {abs(delta_issues)} 个制度问题，优先按召回下降处理，不要直接视为误报减少。")
    if cand_analysis["elapsed_ms"] and base_analysis["elapsed_ms"]:
        ratio = cand_analysis["elapsed_ms"] / max(base_analysis["elapsed_ms"], 1)
        if ratio > 1.3:
            notes.append(f"候选模型耗时上升明显，约为基线的 {ratio:.2f} 倍。")
        elif ratio < 0.75:
            notes.append(f"候选模型速度明显更快，约为基线的 {ratio:.2f} 倍，可作为分层调用的前置模型。")
    if not notes:
        notes.append("这轮样例里候选模型没有出现明显结构性退化，但仍建议继续用真实合同批量验证。")
    return notes


def build_comparison(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("failed") or candidate.get("failed"):
        return {
            "execution_status": "failed",
            "profiles": {
                "baseline": baseline["summary"]["profile"],
                "candidate": candidate["summary"]["profile"],
            },
            "input": baseline["summary"]["input"],
            "baseline_failed": bool(baseline.get("failed")),
            "candidate_failed": bool(candidate.get("failed")),
            "baseline_error": baseline.get("error"),
            "candidate_error": candidate.get("error"),
            "assessment": [
                "至少有一个模型运行未完成，当前结论应优先视为可运行性和工程兼容性问题，而不是纯能力对比。",
                f"基线状态：{baseline['summary']['contract_analysis']['status']}。",
                f"候选状态：{candidate['summary']['contract_analysis']['status']}。",
            ],
        }

    base_summary = baseline["summary"]
    cand_summary = candidate["summary"]
    base_result = baseline["result"]
    cand_result = candidate["result"]
    base_report = baseline["review_report"]
    cand_report = candidate["review_report"]

    comparison = {
        "profiles": {
            "baseline": base_summary["profile"],
            "candidate": cand_summary["profile"],
        },
        "input": base_summary["input"],
        "contract_analysis": {
            "summary_delta": {
                "elapsed_ms_delta": cand_summary["contract_analysis"]["elapsed_ms"] - base_summary["contract_analysis"]["elapsed_ms"],
                "page_count_delta": cand_summary["contract_analysis"]["page_count"] - base_summary["contract_analysis"]["page_count"],
                "section_count_delta": cand_summary["contract_analysis"]["section_count"] - base_summary["contract_analysis"]["section_count"],
                "clause_count_delta": cand_summary["contract_analysis"]["clause_count"] - base_summary["contract_analysis"]["clause_count"],
                "key_fact_count_delta": cand_summary["contract_analysis"]["key_fact_count"] - base_summary["contract_analysis"]["key_fact_count"],
                "audit_focus_count_delta": cand_summary["contract_analysis"]["audit_focus_count"] - base_summary["contract_analysis"]["audit_focus_count"],
                "verification_item_count_delta": cand_summary["contract_analysis"]["verification_item_count"] - base_summary["contract_analysis"]["verification_item_count"],
            },
            "section_title_overlap": compare_lists_exact(
                [item["title"] for item in base_result["sections"]],
                [item["title"] for item in cand_result["sections"]],
            ),
            "clause_title_overlap": compare_lists_exact(
                [item["title"] for item in base_result["clauses"]],
                [item["title"] for item in cand_result["clauses"]],
            ),
            "key_fact_comparison": compare_key_facts(base_result, cand_result),
            "audit_focus_title_overlap": compare_lists_exact(
                [item["title"] for item in baseline["audit_focuses"]],
                [item["title"] for item in candidate["audit_focuses"]],
            ),
            "verification_name_overlap": compare_lists_exact(
                [item["name"] for item in baseline["verification_items"]],
                [item["name"] for item in candidate["verification_items"]],
            ),
        },
        "knowledge_base_review": {
            "detected_category_same": base_summary["knowledge_base_review"]["detected_category"]
            == cand_summary["knowledge_base_review"]["detected_category"],
            "matched_template_same": base_summary["knowledge_base_review"]["matched_template_id"]
            == cand_summary["knowledge_base_review"]["matched_template_id"],
            "issue_count_delta": cand_summary["knowledge_base_review"]["issue_count"]
            - base_summary["knowledge_base_review"]["issue_count"],
            **compare_issue_sets(base_report, cand_report),
        },
    }
    comparison["assessment"] = build_assessment(baseline, candidate, comparison)
    return comparison


def render_markdown_report(baseline: dict[str, Any], candidate: dict[str, Any], comparison: dict[str, Any]) -> str:
    if comparison.get("execution_status") == "failed":
        return "\n".join(
            [
                "# 模型衰退评估报告",
                "",
                "## 运行状态",
                f"- 输入：{comparison['input']['label']}",
                f"- 基线是否失败：{comparison['baseline_failed']}",
                f"- 候选是否失败：{comparison['candidate_failed']}",
                f"- 基线错误：{comparison['baseline_error'] or '无'}",
                f"- 候选错误：{comparison['candidate_error'] or '无'}",
                "",
                "## 结论",
                *[f"- {item}" for item in comparison["assessment"]],
                "",
                "## 输出文件",
                f"- 基线目录：{baseline['paths']['run_root']}",
                f"- 候选目录：{candidate['paths']['run_root']}",
            ]
        ) + "\n"

    base_summary = baseline["summary"]
    cand_summary = candidate["summary"]
    lines = [
        "# 模型衰退评估报告",
        "",
        "## 实验输入",
        f"- 标签：{base_summary['input']['label']}",
        f"- 内置样例：{base_summary['input']['use_builtin_example']}",
        f"- 文件：{base_summary['input']['file_path'] or 'builtin-example'}",
        "",
        "## 模型配置",
        f"- 基线：{base_summary['profile']['name']} | {base_summary['profile']['qwen_model_name']} | {base_summary['profile']['qwen_base_url']}",
        f"- 候选：{cand_summary['profile']['name']} | {cand_summary['profile']['qwen_model_name']} | {cand_summary['profile']['qwen_base_url']}",
        "",
        "## 主工作台结果",
        "| 指标 | 基线 | 候选 | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| 耗时(ms) | {base_summary['contract_analysis']['elapsed_ms']} | {cand_summary['contract_analysis']['elapsed_ms']} | {comparison['contract_analysis']['summary_delta']['elapsed_ms_delta']} |",
        f"| 页数 | {base_summary['contract_analysis']['page_count']} | {cand_summary['contract_analysis']['page_count']} | {comparison['contract_analysis']['summary_delta']['page_count_delta']} |",
        f"| 章节数 | {base_summary['contract_analysis']['section_count']} | {cand_summary['contract_analysis']['section_count']} | {comparison['contract_analysis']['summary_delta']['section_count_delta']} |",
        f"| 条款数 | {base_summary['contract_analysis']['clause_count']} | {cand_summary['contract_analysis']['clause_count']} | {comparison['contract_analysis']['summary_delta']['clause_count_delta']} |",
        f"| 关键事实数 | {base_summary['contract_analysis']['key_fact_count']} | {cand_summary['contract_analysis']['key_fact_count']} | {comparison['contract_analysis']['summary_delta']['key_fact_count_delta']} |",
        f"| 审查关注点数 | {base_summary['contract_analysis']['audit_focus_count']} | {cand_summary['contract_analysis']['audit_focus_count']} | {comparison['contract_analysis']['summary_delta']['audit_focus_count_delta']} |",
        f"| 校验项数 | {base_summary['contract_analysis']['verification_item_count']} | {cand_summary['contract_analysis']['verification_item_count']} | {comparison['contract_analysis']['summary_delta']['verification_item_count_delta']} |",
        "",
        "## 制度审查结果",
        f"- 合同分类是否一致：{comparison['knowledge_base_review']['detected_category_same']}",
        f"- 匹配范本是否一致：{comparison['knowledge_base_review']['matched_template_same']}",
        f"- 基线分类：{base_summary['knowledge_base_review']['detected_category']}",
        f"- 候选分类：{cand_summary['knowledge_base_review']['detected_category']}",
        f"- 基线问题数：{base_summary['knowledge_base_review']['issue_count']}",
        f"- 候选问题数：{cand_summary['knowledge_base_review']['issue_count']}",
        f"- 问题数 Delta：{comparison['knowledge_base_review']['issue_count_delta']}",
        "",
        "## 重合度",
        f"- 章节标题重合率（对基线）：{comparison['contract_analysis']['section_title_overlap']['overlap_ratio_vs_baseline']:.2%}",
        f"- 条款标题重合率（对基线）：{comparison['contract_analysis']['clause_title_overlap']['overlap_ratio_vs_baseline']:.2%}",
        f"- 关键事实标签重合率（对基线）：{comparison['contract_analysis']['key_fact_comparison']['label_overlap']['overlap_ratio_vs_baseline']:.2%}",
        f"- 关键事实值平均相似度：{comparison['contract_analysis']['key_fact_comparison']['value_similarity_avg']:.2%}",
        f"- 审查关注点标题重合率（对基线）：{comparison['contract_analysis']['audit_focus_title_overlap']['overlap_ratio_vs_baseline']:.2%}",
        f"- 校验项名称重合率（对基线）：{comparison['contract_analysis']['verification_name_overlap']['overlap_ratio_vs_baseline']:.2%}",
        f"- 制度问题文本重合率（对基线）：{comparison['knowledge_base_review']['problem_overlap']['overlap_ratio_vs_baseline']:.2%}",
        f"- 制度问题定位重合率（对基线）：{comparison['knowledge_base_review']['clause_location_overlap']['overlap_ratio_vs_baseline']:.2%}",
        "",
        "## 评估结论",
    ]
    for item in comparison["assessment"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 工程建议",
            "- 把 9B 放到前置层，只负责分类、条款抽取、轻量问答；命中低置信度、范本漂移、JSON 校验失败时自动升级到更大模型。",
            "- 为主工作台和制度审查分别建立金标准集，至少单独统计：分类准确率、条款召回、关键事实值准确率、问题召回率、模板匹配准确率。",
            "- 强化结构化约束：保留 `response_format=json_object`，补充更强 few-shot、字段定义、反例提示，并对失败结果做自动重试和 JSON repair。",
            "- 把规则、检索、模板约束前置，减少 9B 需要自由生成的空间，优先让模型做“选择题”和“字段填空题”，不要让它做大段自由裁决。",
            "- 增加线上观测：每次模型切换都把本脚本接入 CI 或定时任务，持续输出 Markdown/JSON 报告，避免只靠人工感受判断衰退。",
            "",
            "## 输出文件",
            f"- 基线目录：{baseline['paths']['run_root']}",
            f"- 候选目录：{candidate['paths']['run_root']}",
        ]
    )
    return "\n".join(lines) + "\n"


async def main() -> None:
    args = parse_args()
    input_spec = build_input(args)
    output_dir = build_output_dir(args, input_spec)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_settings = Settings()
    baseline_profile = build_baseline_profile(base_settings, args.baseline_name)
    candidate_profile = build_candidate_profile(base_settings, args)

    baseline = await run_profile(
        base_settings=base_settings,
        profile=baseline_profile,
        input_spec=input_spec,
        output_dir=output_dir,
    )
    candidate = await run_profile(
        base_settings=base_settings,
        profile=candidate_profile,
        input_spec=input_spec,
        output_dir=output_dir,
    )

    comparison = build_comparison(baseline, candidate)
    ensure_json(output_dir / "baseline_summary.json", baseline["summary"])
    ensure_json(output_dir / "candidate_summary.json", candidate["summary"])
    ensure_json(output_dir / "comparison.json", comparison)

    report = render_markdown_report(baseline, candidate, comparison)
    report_path = output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "report": str(report_path),
                "comparison": str(output_dir / "comparison.json"),
                "baseline_run": baseline["paths"]["run_root"],
                "candidate_run": candidate["paths"]["run_root"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
