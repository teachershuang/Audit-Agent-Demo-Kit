from __future__ import annotations

from typing import Any

from app.logging_utils import app_logger, json_dumps, truncate_for_log
from app.schemas.contract import ContractAnalysisResult
from app.services.qwen_service import QwenService


class ContractClassifier:
    allowed_categories = [
        "建设工程类",
        "买卖合同类",
        "租赁合同类",
        "运输合同类",
        "服务合同类",
        "通用合同类",
    ]

    category_keywords = {
        "建设工程类": ["工程", "施工", "监理", "勘察", "设计", "总承包", "分包", "造价", "项目管理", "建设项目"],
        "买卖合同类": ["采购", "销售", "买卖", "货物", "物资", "设备供货", "材料供应"],
        "租赁合同类": ["租赁", "房屋租赁", "设备租赁", "车辆租赁", "场地租赁"],
        "运输合同类": ["运输", "货运", "物流", "承运", "配送"],
        "服务合同类": ["服务", "技术服务", "咨询", "检测", "评估", "法律服务", "代理", "维护", "运维"],
    }

    def __init__(self, qwen_service: QwenService | None = None) -> None:
        self.qwen_service = qwen_service

    async def classify(self, result: ContractAnalysisResult) -> str:
        detail = await self.classify_detail(result)
        return str(detail["category"])

    async def classify_detail(self, result: ContractAnalysisResult) -> dict[str, Any]:
        llm_detail = await self._classify_with_llm(result)
        if llm_detail:
            return llm_detail

        fallback = self._classify_by_keywords(result)
        app_logger.info(
            json_dumps(
                {
                    "event": "contract_classifier_fallback",
                    "category": fallback["category"],
                    "confidence": fallback["confidence"],
                    "reason": fallback["reason"],
                }
            )
        )
        return fallback

    async def _classify_with_llm(self, result: ContractAnalysisResult) -> dict[str, Any] | None:
        if self.qwen_service is None or not self.qwen_service.is_available:
            return None

        system_prompt = """
你是合同类别识别器，只能在给定类别中选择一个最合适的类别。

可选类别：
1. 建设工程类：工程施工、监理、勘察、设计、总承包、分包、造价咨询、项目管理等。
2. 买卖合同类：采购、供货、销售、设备材料买卖等。
3. 租赁合同类：房屋、设备、车辆、场地租赁等。
4. 运输合同类：货运、物流、承运、配送等。
5. 服务合同类：技术服务、咨询、检测、评估、代理、维护、运维等。
6. 通用合同类：以上都不明显，或信息不足。

判断时优先看：
- 合同标题
- 服务或标的描述
- 核心条款标题
- 双方主体和履约方式

如果只是识别出了“项目名称”但不能说明合同法律关系，不要误判为建设工程类。
如果是“技术服务合同”“咨询服务合同”“检测服务合同”，优先归为服务合同类。

输出 JSON：
{
  "category": "建设工程类|买卖合同类|租赁合同类|运输合同类|服务合同类|通用合同类",
  "confidence": 0.0,
  "reason": "一句话说明",
  "evidence": ["证据1", "证据2"]
}
        """.strip()

        user_prompt = f"""
请识别这份合同的类别。

示例 1
标题：公路工程施工合同
关键条款：工程范围、施工工期、竣工验收、工程价款
输出：{{"category":"建设工程类","confidence":0.95,"reason":"标题和条款都指向工程施工关系","evidence":["工程范围","施工工期"]}}

示例 2
标题：技术服务合同
关键条款：服务内容、成果交付、服务费用、知识产权
输出：{{"category":"服务合同类","confidence":0.94,"reason":"属于技术服务关系","evidence":["技术服务","成果交付"]}}

示例 3
标题：技术服务合同
关键条款：控制测量、纵横断面、激光雷达点云、数据采集
输出：{{"category":"服务合同类","confidence":0.96,"reason":"虽然服务内容与工程相关，但法律关系仍是勘察测量技术服务","evidence":["控制测量","数据采集"]}}

示例 4
标题：设备采购合同
关键条款：货物清单、交货、验收、付款
输出：{{"category":"买卖合同类","confidence":0.94,"reason":"核心是设备供货买卖","evidence":["设备采购","交货"]}}

待识别合同：
文件名：{result.task.fileName}
合同标题候选：{self._candidate_titles(result)}
关键事实：
{self._format_key_facts(result)}

关键条款标题：
{self._format_clause_titles(result)}

关键条款摘要：
{self._format_clause_summaries(result)}
        """.strip()

        schema = {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": self.allowed_categories},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["category", "confidence", "reason", "evidence"],
            "additionalProperties": True,
        }

        try:
            detail = await self.qwen_service.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, schema=schema, timeout=80)
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "contract_classifier_llm_failed",
                        "error": str(exc),
                    }
                )
            )
            return None

        normalized = {
            "category": detail.get("category", "通用合同类"),
            "confidence": float(detail.get("confidence", 0.0) or 0.0),
            "reason": str(detail.get("reason", "")).strip() or "模型未返回理由",
            "evidence": [str(item).strip() for item in detail.get("evidence", []) if str(item).strip()],
            "method": "llm",
        }
        app_logger.info(
            json_dumps(
                {
                    "event": "contract_classifier_llm_success",
                    "result": truncate_for_log(normalized),
                }
            )
        )
        return normalized

    def _classify_by_keywords(self, result: ContractAnalysisResult) -> dict[str, Any]:
        haystack = "\n".join(
            [
                result.task.fileName,
                *[item.title for item in result.sections[:12]],
                *[item.label for item in result.keyFacts[:12]],
                *[item.value for item in result.keyFacts[:12]],
                *[item.title for item in result.clauses[:24]],
                *[item.summary for item in result.clauses[:16]],
            ]
        )

        best_category = "通用合同类"
        best_score = 0
        best_hits: list[str] = []

        for category, keywords in self.category_keywords.items():
            hits = [keyword for keyword in keywords if keyword in haystack]
            score = len(hits)
            if score > best_score:
                best_score = score
                best_category = category
                best_hits = hits

        confidence = 0.55 if best_score else 0.3
        return {
            "category": best_category,
            "confidence": confidence,
            "reason": "基于合同标题、关键事实和条款关键词匹配。",
            "evidence": best_hits[:6],
            "method": "keyword",
        }

    @staticmethod
    def _candidate_titles(result: ContractAnalysisResult) -> str:
        titles: list[str] = []
        for page in result.pages[:3]:
            if page.title and page.title not in titles:
                titles.append(page.title)
        for section in result.sections[:6]:
            if section.title and section.title not in titles:
                titles.append(section.title)
        return "；".join(titles[:6]) or "未提取到明确标题"

    @staticmethod
    def _format_key_facts(result: ContractAnalysisResult) -> str:
        if not result.keyFacts:
            return "未提取到关键事实"
        rows = []
        for fact in result.keyFacts[:12]:
            value = fact.value.strip()[:80] if fact.value else ""
            rows.append(f"- {fact.label}: {value or '空'}")
        return "\n".join(rows)

    @staticmethod
    def _format_clause_titles(result: ContractAnalysisResult) -> str:
        if not result.clauses:
            return "未提取到条款"
        return "\n".join(f"- {clause.title}" for clause in result.clauses[:14])

    @staticmethod
    def _format_clause_summaries(result: ContractAnalysisResult) -> str:
        if not result.clauses:
            return "未提取到条款摘要"
        rows = []
        for clause in result.clauses[:8]:
            summary = clause.summary.strip()[:120] if clause.summary else clause.rawText.strip()[:120]
            rows.append(f"- {clause.title}: {summary}")
        return "\n".join(rows)
