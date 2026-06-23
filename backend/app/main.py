from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.agents.audit_focus_agent import AuditFocusAgent
from app.agents.contract_agent import ContractAgent
from app.agents.contract_parser_agent import ContractParserAgent
from app.agents.planner import Planner
from app.agents.verification_agent import VerificationAgent
from app.api.contracts import get_base_contracts_router
from app.api.debug import get_base_debug_router
from app.api.documents import get_base_documents_router
from app.api.rules import get_base_rules_router
from app.api.base_support import KnowledgeBaseService
from app.classifier.contract_classifier import ContractClassifier
from app.comparator.template_comparator import TemplateComparator
from app.config import get_settings
from app.embedding.embedding_client import EmbeddingClient
from app.extractor.contract_schema_extractor import ContractSchemaExtractor
from app.llm.llm_client import LLMClient
from app.logging_utils import app_logger, frontend_logger, json_dumps, truncate_for_log
from app.parser.docx_parser import DOCXParser
from app.parser.pdf_parser import PDFParser
from app.redis_store.clause_store import ClauseStore
from app.redis_store.document_store import DocumentStore
from app.redis_store.indexes import RedisIndexManager
from app.redis_store.redis_client import RedisClientFactory
from app.redis_store.report_store import ReportStore
from app.redis_store.review_task_store import ReviewTaskStore
from app.redis_store.rule_store import RuleStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.policy_retriever import PolicyRetriever
from app.retrieval.template_retriever import TemplateRetriever
from app.reviewer.issue_generator import IssueGenerator
from app.reviewer.main_project_bridge import MainProjectReviewBridge
from app.reviewer.report_generator import ReportGenerator
from app.reviewer.review_pipeline import ReviewPipeline
from app.routers.audit import get_audit_router
from app.routers.config import get_config_router
from app.routers.contracts import get_contract_router
from app.routers.logs import get_logs_router
from app.routers.runtime_models import get_runtime_models_router
from app.routers.rules import get_rules_router
from app.rule_engine.rule_runner import RuleRunner
from app.services.confidence_service import ConfidenceService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.model_probe_service import ModelProbeService
from app.services.ocr_service import OCRService
from app.services.paddle_ocr_service import PaddleOCRService
from app.services.qwen_service import QwenService
from app.services.relation_config_service import RelationConfigService
from app.services.report_preview_service import ReportPreviewService
from app.services.runtime_model_profile_service import RuntimeModelProfileService
from app.splitter.clause_splitter import ClauseSplitter
from app.splitter.policy_splitter import PolicySplitter
from app.splitter.template_splitter import TemplateSplitter
from app.storage.local_store import LocalStore
from app.tools.rule_engine_adapter import RuleEngineAdapter

settings = get_settings()
store = LocalStore(base_dir=Path(__file__).resolve().parents[1] / settings.storage_dir)

qwen_service = QwenService(settings)
document_service = DocumentService()
paddle_ocr_service = PaddleOCRService(
    python_executable=settings.paddle_python_executable,
    timeout_seconds=settings.paddle_ocr_timeout_seconds,
    batch_size=settings.paddle_ocr_batch_size,
    mode=settings.paddle_service_mode,
    remote_base_url=settings.paddle_remote_base_url,
    remote_endpoint=settings.paddle_remote_endpoint,
    remote_health_path=settings.paddle_remote_health_path,
    remote_timeout_seconds=settings.paddle_remote_timeout_seconds,
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
audit_focus_agent = AuditFocusAgent(qwen_service=qwen_service, settings=settings)
verification_agent = VerificationAgent(qwen_service=qwen_service)
relation_config_service = RelationConfigService(store=store)
rule_engine_adapter = RuleEngineAdapter(settings=settings)
model_probe_service = ModelProbeService(settings)
runtime_model_profile_service = RuntimeModelProfileService(
    settings=settings,
    qwen_service=qwen_service,
    paddle_ocr_service=paddle_ocr_service,
    model_probe_service=model_probe_service,
)
redis_factory = RedisClientFactory(settings)
redis_client = redis_factory.get_client()
embedding_client = EmbeddingClient(settings)
llm_client = LLMClient(settings)
document_store = DocumentStore(redis_client)
rule_store = RuleStore(redis_client)
report_store = ReportStore(redis_client)
review_task_store = ReviewTaskStore(redis_client)
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
main_project_review_bridge = MainProjectReviewBridge()
knowledge_base_service = KnowledgeBaseService(
    storage_root=store.base_dir,
    document_store=document_store,
    clause_store=clause_store,
    rule_store=rule_store,
    embedding_client=embedding_client,
    llm_client=llm_client,
    pdf_parser=PDFParser(),
    docx_parser=DOCXParser(),
    policy_splitter=PolicySplitter(),
    template_splitter=TemplateSplitter(),
    clause_splitter=ClauseSplitter(),
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
report_preview_service = ReportPreviewService(
    local_store=store,
    report_store=report_store,
    storage_root=store.base_dir,
)
contract_agent = ContractAgent(
    document_service=document_service,
    ocr_service=ocr_service,
    parser_agent=parser_agent,
    audit_focus_agent=audit_focus_agent,
    verification_agent=verification_agent,
    evidence_service=evidence_service,
    confidence_service=confidence_service,
    planner=planner,
    storage_dir=store.base_dir,
    rule_engine_adapter=rule_engine_adapter,
)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.state.runtime_models = {}
app_logger.setLevel(settings.log_level.upper())
frontend_logger.setLevel(settings.log_level.upper())
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    get_contract_router(
        store=store,
        agent=contract_agent,
        review_pipeline=review_pipeline,
        review_bridge=main_project_review_bridge,
    )
)
app.include_router(get_config_router(relation_config_service=relation_config_service))
app.include_router(
    get_audit_router(
        store=store,
        agent=contract_agent,
        review_pipeline=review_pipeline,
        review_bridge=main_project_review_bridge,
    )
)
app.include_router(get_logs_router())
app.include_router(get_runtime_models_router(runtime_model_profile_service))
app.include_router(get_rules_router(store=store, adapter=rule_engine_adapter))
app.include_router(get_base_documents_router(knowledge_base_service))
app.include_router(get_base_rules_router(rule_store, knowledge_base_service))
app.include_router(
    get_base_contracts_router(
        review_pipeline=review_pipeline,
        report_store=report_store,
        review_task_store=review_task_store,
        local_store=store,
        report_preview_service=report_preview_service,
    )
)
app.include_router(
    get_base_debug_router(
        clause_store=clause_store,
        policy_retriever=policy_retriever,
        hybrid_retriever=hybrid_retriever,
    )
)

try:
    RedisIndexManager(redis_client, settings).ensure_indexes()
except Exception as exc:
    app_logger.warning(json_dumps({"event": "redis_index_init_failed", "error": str(exc)}))


@app.on_event("startup")
async def startup_model_probe() -> None:
    app.state.runtime_models = await runtime_model_profile_service.initialize()
    app_logger.info(
        json_dumps(
            {
                "event": "startup_model_probe_completed",
                "runtimeModels": app.state.runtime_models,
                "runtimeProfile": runtime_model_profile_service.snapshot(),
            }
        )
    )


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = perf_counter()
    request_body_bytes = await request.body()
    request_payload = _summarize_http_body(
        request_body_bytes,
        request.headers.get("content-type"),
        max_chars=settings.log_body_max_chars,
    )
    app_logger.debug(
        json_dumps(
            {
                "event": "request_started",
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
                "contentType": request.headers.get("content-type"),
                "client": request.client.host if request.client else None,
                "request": request_payload,
            }
        )
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        detail = str(exc).strip() or exc.__class__.__name__
        app_logger.exception(
            json_dumps(
                {
                    "event": "request_exception",
                    "method": request.method,
                    "path": request.url.path,
                    "query": dict(request.query_params),
                    "durationMs": duration_ms,
                    "client": request.client.host if request.client else None,
                    "request": request_payload,
                    "error": detail,
                }
            )
        )
        return JSONResponse(status_code=500, content={"detail": detail})

    duration_ms = round((perf_counter() - started) * 1000, 2)
    response_payload = _summarize_http_body(
        getattr(response, "body", b"") if hasattr(response, "body") else b"",
        response.headers.get("content-type"),
        max_chars=settings.log_body_max_chars,
    )
    app_logger.info(
        json_dumps(
            {
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
                "status": response.status_code,
                "durationMs": duration_ms,
                "client": request.client.host if request.client else None,
                "request": request_payload,
                "response": response_payload,
            }
        )
    )
    return response


@app.get("/health")
async def health():
    runtime_models = getattr(app.state, "runtime_models", {}) or {}
    text_runtime = runtime_models.get("text") or {}
    vision_runtime = runtime_models.get("vision") or {}
    llm_runtime = runtime_models.get("review_llm") or {}
    embedding_runtime = runtime_models.get("embedding") or {}
    return {
        "status": "ok",
        "app": settings.app_name,
        "mode": runtime_model_profile_service.active_profile_id,
        "active_profile_id": runtime_model_profile_service.active_profile_id,
        "active_profile_label": runtime_model_profile_service.profiles[runtime_model_profile_service.active_profile_id].label,
        "text_model": text_runtime.get("resolved_model") or settings.qwen_model_name,
        "vision_model": vision_runtime.get("resolved_model") or settings.qwen_vision_model_name,
        "llm_model": llm_runtime.get("resolved_model") or settings.llm_model,
        "embedding_model": embedding_runtime.get("resolved_model") or settings.embedding_model,
        "runtime_models": runtime_models,
        "knowledge_base_enabled": True,
    }


def _summarize_http_body(body: bytes, content_type: str | None, *, max_chars: int) -> dict[str, object] | None:
    if not body:
        return None
    content_type = (content_type or "").lower()
    byte_size = len(body)
    if byte_size > 2_500_000:
        return {
            "contentType": content_type or "unknown",
            "bytes": byte_size,
            "note": "body omitted because it is larger than 2.5 MB",
        }
    if "multipart/form-data" in content_type:
        return {
            "contentType": content_type,
            "bytes": byte_size,
            "note": "multipart body omitted; see upload metadata in application logs",
        }
    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = body.decode("utf-8", errors="replace")
        return {"contentType": content_type, "body": truncate_for_log(payload, max_chars=max_chars)}
    if "application/x-www-form-urlencoded" in content_type or "text/" in content_type:
        return {
            "contentType": content_type,
            "body": truncate_for_log(body.decode("utf-8", errors="replace"), max_chars=max_chars),
        }
    return {
        "contentType": content_type or "unknown",
        "bytes": byte_size,
        "note": "binary body omitted",
    }
