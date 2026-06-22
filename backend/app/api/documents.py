from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pathlib import Path

from fastapi.responses import FileResponse

from app.api.base_support import KnowledgeBaseService
from app.schemas.document import DocumentAbolishRequest, DocumentPatchRequest, DocumentStatusPatch


def _today_ts() -> int:
    return int(datetime.now().strftime("%Y%m%d"))


def get_base_documents_router(service: KnowledgeBaseService):
    router = APIRouter(prefix="/api/base/documents", tags=["base-documents"])

    @router.post("/upload")
    async def upload_document(
        file: UploadFile = File(...),
        doc_type: str = Form(...),
        version: str = Form(default="v1"),
        issuer: str | None = Form(default=None),
        effective_date: str | None = Form(default=None),
        effective_ts: int | None = Form(default=None),
        category: str | None = Form(default=None),
        confidential_level: str = Form(default="internal"),
    ):
        content = await file.read()
        document, clauses, rules = await service.ingest_document(
            file_name=file.filename or "uploaded.pdf",
            file_bytes=content,
            doc_type=doc_type,
            version=version,
            issuer=issuer,
            effective_date=effective_date,
            effective_ts=effective_ts or _today_ts(),
            category=category,
            confidential_level=confidential_level,
        )
        return {
            "document": document.model_dump(),
            "clause_count": len(clauses),
            "rule_count": len(rules),
            "rules": [rule.model_dump() for rule in rules],
        }

    @router.get("")
    async def list_documents():
        return [item.model_dump() for item in service.document_store.list()]

    @router.get("/{doc_id}")
    async def get_document(doc_id: str):
        document = service.document_store.get(doc_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    @router.patch("/{doc_id}")
    async def patch_document(doc_id: str, payload: DocumentPatchRequest):
        patch = payload.model_dump(exclude_none=True)
        document = service.patch_document(doc_id, **patch)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    @router.get("/{doc_id}/metadata")
    async def get_document_metadata(doc_id: str, include_clauses: bool = False):
        payload = service.document_metadata(doc_id, include_clauses=include_clauses)
        if payload is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return payload

    @router.get("/{doc_id}/pages/{page}/image")
    async def get_document_page_image(doc_id: str, page: int):
        image_path = service.page_image_path(doc_id, page)
        if image_path is None or not image_path.exists():
            raise HTTPException(status_code=404, detail="Page image not found")
        return FileResponse(image_path)

    @router.get("/{doc_id}/file")
    async def get_document_file(doc_id: str):
        document = service.document_store.get(doc_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        file_path = Path(document.source_file)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Source file not found")
        media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else None
        return FileResponse(file_path, media_type=media_type, headers={"Content-Disposition": "inline"})

    @router.get("/{doc_id}/clauses")
    async def get_document_clauses(doc_id: str):
        payload = service.document_clause_list(doc_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return payload

    @router.get("/clauses/{clause_id}")
    async def get_clause_metadata(clause_id: str):
        payload = service.clause_metadata(clause_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Clause not found")
        return payload

    @router.patch("/{doc_id}/status")
    async def patch_status(doc_id: str, payload: DocumentStatusPatch):
        document = service.document_store.update_fields(doc_id, status=payload.status)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if payload.status in {"abolished", "superseded", "expired"}:
            service.clause_store.update_document_status(doc_id, status=payload.status, abolish_ts=_today_ts())
        return document

    @router.post("/{doc_id}/abolish")
    async def abolish_document(doc_id: str, payload: DocumentAbolishRequest):
        document = service.abolish_document(
            doc_id,
            payload.abolish_ts or _today_ts(),
            payload.abolish_date,
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    @router.post("/{old_doc_id}/replace/{new_doc_id}")
    async def replace_document(old_doc_id: str, new_doc_id: str):
        old_doc, new_doc = service.replace_document(old_doc_id, new_doc_id)
        if old_doc is None or new_doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"old_document": old_doc.model_dump(), "new_document": new_doc.model_dump()}

    return router
