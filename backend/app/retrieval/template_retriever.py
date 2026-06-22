from __future__ import annotations

from typing import Any

from app.logging_utils import app_logger, json_dumps, truncate_for_log
from app.redis_store.clause_store import ClauseStore
from app.schemas.clause import ClauseRecord
from app.schemas.review import ContractSchema
from app.services.qwen_service import QwenService


class TemplateRetriever:
    def __init__(self, clause_store: ClauseStore, qwen_service: QwenService | None = None) -> None:
        self.clause_store = clause_store
        self.qwen_service = qwen_service

    async def match_template(
        self,
        contract_schema: ContractSchema,
        *,
        selected_template_id: str | None,
        today: int,
    ) -> dict | None:
        if selected_template_id:
            clauses = self.clause_store.list(template_id=selected_template_id)
            if clauses:
                return self._build_match(clauses, score=999.0, match_reason="manual_selected")

        keywords = [item["title"] for item in contract_schema.clauses[:10]]
        candidates = self.clause_store.template_candidates(
            detected_category=contract_schema.detected_category,
            keywords=keywords,
            today=today,
        )
        if not candidates:
            return None

        rescored = self._rescore_candidates(contract_schema, candidates)
        top_candidates = rescored[:5]
        llm_choice = await self._rerank_with_llm(contract_schema, top_candidates)
        chosen = self._pick_candidate(top_candidates, llm_choice)
        if chosen is None:
            return None

        clauses = self.clause_store.list(template_id=chosen["template_id"])
        if not clauses:
            return None
        return self._build_match(
            clauses,
            score=float(chosen.get("score", 0.0)),
            match_reason=str(chosen.get("match_reason") or "heuristic"),
            match_confidence=float(chosen.get("match_confidence", 0.0) or 0.0),
        )

    def _rescore_candidates(self, contract_schema: ContractSchema, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        profile_text = self._build_contract_profile(contract_schema)
        measurement_terms = ["测量", "测绘", "勘察测量", "控制测量", "纵横断面", "点云", "激光雷达", "数据采集", "勘测"]
        audit_terms = ["审计", "审计报告", "注册会计师", "被审计单位", "审计准则", "审计成果"]
        technical_service_terms = ["技术服务合同", "专项技术服务", "服务内容", "成果交付", "数据采集服务"]
        engineering_survey_terms = ["工程勘察", "工程设计", "勘察设计", "设计服务"]
        detection_terms = ["检测", "检验", "试验"]
        legal_terms = ["法律服务", "律师", "法律意见"]
        appraisal_terms = ["评估", "资产评估"]

        rescored: list[dict[str, Any]] = []
        for candidate in candidates:
            item = dict(candidate)
            template_name = str(item.get("template_name") or "")
            category_lv2 = str(item.get("category_lv2") or "")
            score = float(item.get("score", 0.0))
            reasons: list[str] = []

            if any(term in profile_text for term in technical_service_terms):
                if "技术服务合同" in template_name:
                    score += 12.0
                    reasons.append("合同标题与技术服务模板直接对应")
                if "第三方审计合同" in template_name:
                    score -= 10.0
                    reasons.append("合同标题明确为技术服务，不应优先匹配审计模板")

            if any(term in profile_text for term in measurement_terms):
                if "技术服务合同" in template_name:
                    score += 10.0
                    reasons.append("合同内容包含测量/点云/数据采集等技术服务特征")
                if "工程勘察合同" in template_name:
                    score += 6.0
                    reasons.append("合同内容包含勘察测量特征")
                if "第三方审计合同" in template_name:
                    score -= 12.0
                    reasons.append("合同内容与审计业务特征明显不符")

            if any(term in profile_text for term in audit_terms):
                if "第三方审计合同" in template_name:
                    score += 14.0
                    reasons.append("合同内容出现审计业务特征")
            elif "第三方审计合同" in template_name:
                score -= 5.0
                reasons.append("未出现审计业务关键词")

            if any(term in profile_text for term in detection_terms):
                if "检测委托合同" in template_name:
                    score += 8.0
                    reasons.append("合同内容出现检测类特征")

            if any(term in profile_text for term in legal_terms) and "法律服务合同" in template_name:
                score += 10.0
                reasons.append("合同内容出现法律服务特征")

            if any(term in profile_text for term in appraisal_terms) and "资产评估服务合同" in template_name:
                score += 10.0
                reasons.append("合同内容出现评估类特征")

            if any(term in profile_text for term in engineering_survey_terms) and category_lv2 == "工程勘察设计合同":
                score += 4.0
                reasons.append("合同内容与工程勘察设计存在关联")

            item["score"] = score
            item["heuristic_reasons"] = reasons
            rescored.append(item)

        rescored.sort(key=lambda current: current["score"], reverse=True)
        app_logger.info(
            json_dumps(
                {
                    "event": "template_candidates_rescored",
                    "detectedCategory": contract_schema.detected_category,
                    "topCandidates": truncate_for_log(rescored[:5]),
                }
            )
        )
        return rescored

    async def _rerank_with_llm(self, contract_schema: ContractSchema, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self.qwen_service is None or not self.qwen_service.is_available or not candidates:
            return None

        system_prompt = """
你是合同范本匹配器。输入一份待审合同摘要和若干候选范本，请从候选范本中选出最适合的一份。

判断原则：
1. 优先看合同标题、服务对象、成果物、履约方式。
2. “技术服务合同”“勘察测量服务”“控制测量”“数据采集”“点云”“纵横断面”等特征，优先匹配技术服务或勘察相关模板。
3. 只有出现“审计报告”“注册会计师”“审计准则”“被审计单位”等特征时，才考虑审计模板。
4. 如果没有任何候选明显合适，返回最接近的一项并说明保留意见。

输出 JSON：
{
  "template_id": "候选中的 template_id",
  "confidence": 0.0,
  "reason": "一句话说明"
}
        """.strip()

        candidate_lines: list[str] = []
        for candidate in candidates:
            template_id = str(candidate.get("template_id") or "")
            template_name = str(candidate.get("template_name") or "")
            category_lv1 = str(candidate.get("category_lv1") or "")
            category_lv2 = str(candidate.get("category_lv2") or "")
            clauses = self.clause_store.list(template_id=template_id)[:6]
            clause_titles = "；".join(item.title for item in clauses if item.title) or "未提取到条款标题"
            page_start = clauses[0].page_start if clauses else None
            page_end = clauses[-1].page_end if clauses else None
            usage_profile, usage_basis = self._build_template_usage_profile(template_name, clauses)
            candidate_lines.append(
                f"- {template_id} | {template_name} | {category_lv1}/{category_lv2} | 页码范围：{page_start}-{page_end} | 模板用途画像：{usage_profile or '未识别'} | 判定依据：{' / '.join(usage_basis) if usage_basis else clause_titles}"
            )

        user_prompt = f"""
待审合同类别：{contract_schema.detected_category}
待审合同摘要：
{self._build_contract_profile(contract_schema)}

候选范本：
{chr(10).join(candidate_lines)}
        """.strip()

        schema = {
            "type": "object",
            "properties": {
                "template_id": {"type": "string"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["template_id", "confidence", "reason"],
            "additionalProperties": True,
        }

        try:
            choice = await self.qwen_service.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, schema=schema, timeout=80)
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "template_rerank_llm_failed",
                        "error": str(exc),
                    }
                )
            )
            return None

        app_logger.info(
            json_dumps(
                {
                    "event": "template_rerank_llm_success",
                    "choice": truncate_for_log(choice),
                }
            )
        )
        return choice

    @staticmethod
    def _pick_candidate(candidates: list[dict[str, Any]], llm_choice: dict[str, Any] | None) -> dict[str, Any] | None:
        if not candidates:
            return None
        if llm_choice:
            selected_id = str(llm_choice.get("template_id") or "")
            confidence = float(llm_choice.get("confidence", 0.0) or 0.0)
            for candidate in candidates:
                if candidate.get("template_id") == selected_id:
                    item = dict(candidate)
                    item["match_reason"] = llm_choice.get("reason") or "llm_rerank"
                    item["match_confidence"] = confidence
                    if confidence >= 0.55:
                        return item
                    break

        fallback = dict(candidates[0])
        fallback["match_reason"] = "heuristic_top_candidate"
        fallback["match_confidence"] = 0.5
        return fallback

    @staticmethod
    def _build_contract_profile(contract_schema: ContractSchema) -> str:
        fields = contract_schema.fields
        lines = [
            f"合同类别：{contract_schema.detected_category}",
            f"合同标的：{fields.get('contract_subject') or '未提取'}",
            f"服务内容：{fields.get('contract_subject') or '未提取'}",
            f"付款条款：{fields.get('payment_terms') or '未提取'}",
        ]
        clause_lines = []
        for clause in contract_schema.clauses[:8]:
            title = str(clause.get("title") or "")
            summary = str(clause.get("summary") or clause.get("rawText") or "")[:100]
            clause_lines.append(f"- {title}: {summary}")
        return "\n".join(lines + ["关键条款："] + clause_lines)

    @staticmethod
    def _build_match(
        clauses: list[ClauseRecord],
        score: float | None = None,
        match_reason: str | None = None,
        match_confidence: float | None = None,
    ) -> dict:
        first = clauses[0]
        return {
            "template_id": first.template_id,
            "template_name": first.template_name,
            "category_lv1": first.category_lv1,
            "category_lv2": first.category_lv2,
            "score": score,
            "match_reason": match_reason,
            "match_confidence": match_confidence,
            "clauses": clauses,
        }

    @staticmethod
    def _build_template_usage_profile(template_name: str, clauses: list[ClauseRecord]) -> tuple[str | None, list[str]]:
        haystack = "\n".join(
            [template_name]
            + [(clause.title or "").strip() for clause in clauses[:8]]
            + [(clause.content or "").strip()[:160] for clause in clauses[:6]]
        )
        def match_keywords(keywords: list[str]) -> list[str]:
            return [keyword for keyword in keywords if keyword in haystack][:4]

        if "仓储" in template_name:
            occupancy_basis = match_keywords(["房屋", "移交日", "保证金", "物业", "场地", "承重", "退场"])
            service_basis = match_keywords(["仓储服务", "入库", "出库", "保管", "存货", "货物", "盘点", "仓储费", "装卸"])
            if len(occupancy_basis) >= max(2, len(service_basis)):
                return "场地占用型仓储合同", occupancy_basis
            if service_basis:
                return "标准仓储服务型合同", service_basis
            return "通用仓储合同模板", match_keywords(["仓储", "保管", "货物"])

        if "技术服务" in template_name:
            measurement_basis = match_keywords(["测量", "测绘", "点云", "激光雷达", "数据采集", "控制测量", "纵横断面"])
            if measurement_basis:
                return "测量采集型技术服务模板", measurement_basis
            return "通用技术服务模板", match_keywords(["技术服务", "服务费"])

        if "审计" in template_name:
            audit_basis = match_keywords(["审计", "审计报告", "注册会计师", "被审计单位", "审计准则"])
            if audit_basis:
                return "审计鉴证服务型模板", audit_basis

        return None, []
