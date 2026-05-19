from __future__ import annotations

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
from app.config import get_settings
from app.logging_utils import app_logger, json_dumps
from app.routers.audit import get_audit_router
from app.routers.config import get_config_router
from app.routers.contracts import get_contract_router
from app.routers.logs import get_logs_router
from app.routers.rules import get_rules_router
from app.services.confidence_service import ConfidenceService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.ocr_service import OCRService
from app.services.paddle_ocr_service import PaddleOCRService
from app.services.qwen_service import QwenService
from app.services.relation_config_service import RelationConfigService
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
relation_config_service = RelationConfigService(store=store)
rule_engine_adapter = RuleEngineAdapter(settings=settings)
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(get_contract_router(store=store, agent=contract_agent))
app.include_router(get_config_router(relation_config_service=relation_config_service))
app.include_router(get_audit_router(store=store, agent=contract_agent))
app.include_router(get_logs_router())
app.include_router(get_rules_router(store=store, adapter=rule_engine_adapter))


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started = perf_counter()
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
                    "error": detail,
                }
            )
        )
        return JSONResponse(status_code=500, content={"detail": detail})

    duration_ms = round((perf_counter() - started) * 1000, 2)
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
            }
        )
    )
    return response


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "mode": "qwen" if settings.qwen_api_key else "not_configured",
    }
