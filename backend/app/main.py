from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.audit_focus_agent import AuditFocusAgent
from app.agents.contract_agent import ContractAgent
from app.agents.planner import Planner
from app.agents.verification_agent import VerificationAgent
from app.config import get_settings
from app.routers.audit import get_audit_router
from app.routers.config import get_config_router
from app.routers.contracts import get_contract_router
from app.services.confidence_service import ConfidenceService
from app.services.document_service import DocumentService
from app.services.evidence_service import EvidenceService
from app.services.ocr_service import OCRService
from app.services.qwen_service import QwenService
from app.services.relation_config_service import RelationConfigService
from app.storage.local_store import LocalStore
from app.tools.mock_ocr_tool import MockOcrTool

settings = get_settings()
store = LocalStore(base_dir=Path(__file__).resolve().parents[1] / settings.storage_dir)

qwen_service = QwenService(settings)
document_service = DocumentService()
ocr_service = OCRService(mock_ocr_tool=MockOcrTool())
evidence_service = EvidenceService()
confidence_service = ConfidenceService()
planner = Planner()
audit_focus_agent = AuditFocusAgent(qwen_service=qwen_service)
verification_agent = VerificationAgent()
relation_config_service = RelationConfigService(store=store)
contract_agent = ContractAgent(
    document_service=document_service,
    ocr_service=ocr_service,
    audit_focus_agent=audit_focus_agent,
    verification_agent=verification_agent,
    evidence_service=evidence_service,
    confidence_service=confidence_service,
    planner=planner,
)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(get_contract_router(store=store, agent=contract_agent))
app.include_router(get_config_router(relation_config_service=relation_config_service))
app.include_router(get_audit_router(store=store, agent=contract_agent))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "mode": "mock" if settings.use_mock_model or not settings.qwen_api_key else "qwen",
    }
