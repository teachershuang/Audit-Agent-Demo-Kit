from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import asyncio
from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4

from app.data.default_relations import build_default_relations
from app.schemas.agent import AgentStep
from app.schemas.audit import AuditFocus, VerificationItem
from app.schemas.contract import ContractAnalysisResult, ContractTask, TaskStatus
from app.schemas.relation import RelationConfig


@dataclass
class TaskRecord:
    task: ContractTask
    file_path: Optional[Path] = None
    use_builtin_example: bool = True
    result: ContractAnalysisResult | None = None
    audit_focuses: list[AuditFocus] = field(default_factory=list)
    verification_items: list[VerificationItem] = field(default_factory=list)
    agent_steps: list[AgentStep] = field(default_factory=list)
    started_at_perf: float = field(default_factory=perf_counter)
    analysis_job: asyncio.Task | None = None


class LocalStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, TaskRecord] = {}
        self._relations: list[RelationConfig] = build_default_relations()

    def create_task(
        self,
        file_name: str,
        model_name: str,
        use_builtin_example: bool,
        file_path: Path | None = None,
    ) -> TaskRecord:
        task_id = f"task_{uuid4().hex[:8]}"
        task = ContractTask(
            taskId=task_id,
            fileName=file_name,
            status=TaskStatus.PROCESSING,
            createdAt=datetime.now().astimezone().isoformat(timespec="seconds"),
            modelName=model_name,
            confidenceOverview={"overall": 0.0, "sections": 0.0, "clauses": 0.0, "audit": 0.0, "warnings": 0},
            progressPercent=4,
            currentStage="file_received",
            stageDetail="文件已接收，等待开始分析。",
            elapsedMs=0,
        )
        record = TaskRecord(
            task=task,
            file_path=file_path,
            use_builtin_example=use_builtin_example,
        )
        self._tasks[task_id] = record
        return record

    def get_task(self, task_id: str) -> TaskRecord:
        if task_id not in self._tasks:
            raise KeyError(task_id)
        return self._tasks[task_id]

    def save_result(
        self,
        task_id: str,
        result: ContractAnalysisResult,
        audit_focuses: list[AuditFocus],
        verification_items: list[VerificationItem],
        agent_steps: list[AgentStep],
    ) -> TaskRecord:
        record = self.get_task(task_id)
        result.task.elapsedMs = int((perf_counter() - record.started_at_perf) * 1000)
        result.task.progressPercent = 100
        result.task.currentStage = "completed"
        result.task.stageDetail = "分析结果已生成，可查看章节、条款、关注事项与证据链。"
        record.task = result.task
        record.result = result
        record.audit_focuses = audit_focuses
        record.verification_items = verification_items
        record.agent_steps = agent_steps
        return record

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        progress_percent: int | None = None,
        current_stage: str | None = None,
        stage_detail: str | None = None,
    ) -> ContractTask:
        record = self.get_task(task_id)
        if status is not None:
            record.task.status = status
        if progress_percent is not None:
            record.task.progressPercent = max(0, min(100, progress_percent))
        if current_stage is not None:
            record.task.currentStage = current_stage
        if stage_detail is not None:
            record.task.stageDetail = stage_detail
        record.task.elapsedMs = int((perf_counter() - record.started_at_perf) * 1000)
        return record.task

    def list_relations(self) -> list[RelationConfig]:
        return self._relations

    def set_relations(self, relations: list[RelationConfig]) -> list[RelationConfig]:
        self._relations = relations
        return self._relations

    def upsert_relation(self, relation: RelationConfig) -> RelationConfig:
        exists = False
        updated: list[RelationConfig] = []
        for item in self._relations:
            if item.id == relation.id:
                updated.append(relation)
                exists = True
            else:
                updated.append(item)
        if not exists:
            updated.append(relation)
        self._relations = updated
        return relation

    def delete_relation(self, relation_id: str) -> None:
        self._relations = [item for item in self._relations if item.id != relation_id]
