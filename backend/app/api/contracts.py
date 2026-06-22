from __future__ import annotations

import asyncio
from datetime import datetime
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.reviewer.review_pipeline import ReviewPipeline
from app.schemas.review import ReviewRequest, ReviewResponse, ReviewTaskRecord, SourceTaskSummary
from app.services.report_preview_service import ReportPreviewService
from app.storage.local_store import LocalStore


def get_base_contracts_router(
    *,
    review_pipeline: ReviewPipeline,
    report_store,
    review_task_store,
    local_store: LocalStore,
    report_preview_service: ReportPreviewService,
):
    router = APIRouter(prefix="/api/base/contracts", tags=["base-contracts"])

    @router.get("/source-tasks", response_model=list[SourceTaskSummary])
    async def list_source_tasks():
        items = [
            SourceTaskSummary(
                task_id=record.task.taskId,
                file_name=record.task.fileName,
                status=record.task.status,
                created_at=record.task.createdAt,
            )
            for record in local_store.list_tasks()
            if record.result is not None
        ]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def execute_review_task(task_id: str, payload: ReviewRequest) -> None:
        review_task_store.update(
            task_id,
            status="running",
            message="制度条款检索、范本匹配与规则校验正在执行，首次可能持续 1 到 3 分钟。",
        )
        try:
            result = asyncio.run(review_pipeline.review_contract(payload))
            report = result["report"]
            review_task_store.update(
                task_id,
                status="completed",
                message="审查完成，可查看结构化字段、问题列表和依据条款。",
                contract_id=report.contract_id,
                issue_count=len(report.issues),
                detected_category=report.detected_category,
                matched_template=report.matched_template,
                error=None,
            )
        except KeyError:
            review_task_store.update(
                task_id,
                status="failed",
                message="未找到对应的主项目合同任务。",
                error="Source task not found",
            )
        except ValueError as exc:
            review_task_store.update(
                task_id,
                status="failed",
                message="审查任务未通过前置校验。",
                error=str(exc),
            )
        except Exception as exc:
            review_task_store.update(
                task_id,
                status="failed",
                message="审查执行失败，请稍后重试。",
                error=str(exc),
            )

    @router.post("/review", response_model=ReviewResponse)
    async def review_contract(payload: ReviewRequest):
        try:
            result = await review_pipeline.review_contract(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Source task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        report = result["report"]
        return ReviewResponse(
            contract_id=report.contract_id,
            status=report.status,
            matched_template=report.matched_template,
            detected_category=report.detected_category,
            issue_count=len(report.issues),
        )

    @router.post("/review/start", response_model=ReviewTaskRecord)
    async def start_review_contract(payload: ReviewRequest):
        now = datetime.now().isoformat(timespec="seconds")
        task = ReviewTaskRecord(
            task_id=f"review_{uuid4().hex[:10]}",
            source_task_id=payload.source_task_id,
            selected_template_id=payload.selected_template_id,
            status="queued",
            message="任务已受理，正在准备制度检索与范本匹配。",
            created_at=now,
            updated_at=now,
        )
        review_task_store.save(task)
        Thread(target=execute_review_task, args=(task.task_id, payload), daemon=True).start()
        return task

    @router.get("/review-tasks/{task_id}", response_model=ReviewTaskRecord)
    async def get_review_task(task_id: str):
        task = review_task_store.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Review task not found")
        return task

    @router.get("/{contract_id}/schema")
    async def get_contract_schema(contract_id: str):
        schema = report_store.get_schema(contract_id)
        if schema is None:
            raise HTTPException(status_code=404, detail="Schema not found")
        return schema

    @router.get("/{contract_id}/report")
    async def get_contract_report(contract_id: str):
        report = report_preview_service.build_report_payload(contract_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    @router.get("/{contract_id}/issues")
    async def get_contract_issues(contract_id: str):
        report = report_store.get_report(contract_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return [item.model_dump() for item in report.issues]

    @router.get("/{contract_id}/issues/{issue_id}/snippet")
    async def get_issue_snippet(contract_id: str, issue_id: str):
        snippet_path = report_preview_service.get_issue_snippet_path(contract_id, issue_id)
        if snippet_path is None or not snippet_path.exists():
            raise HTTPException(status_code=404, detail="Issue snippet not found")
        return FileResponse(snippet_path)

    return router
