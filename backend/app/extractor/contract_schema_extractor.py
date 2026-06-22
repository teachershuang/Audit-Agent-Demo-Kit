from __future__ import annotations

from datetime import datetime

from app.schemas.contract import ClauseTag, ContractAnalysisResult, KeyFact
from app.schemas.review import ContractSchema


class ContractSchemaExtractor:
    field_aliases = {
        "contract_number": ["合同编号", "协议编号"],
        "contract_parties": ["甲方", "乙方", "合同主体", "主体"],
        "unified_social_credit_code": ["统一社会信用代码", "纳税人识别号"],
        "legal_representative": ["法定代表人", "授权代表", "签章"],
        "contract_subject": ["合同标的", "标的", "服务内容", "采购内容"],
        "quantity": ["数量"],
        "quality": ["质量", "规格"],
        "price": ["价款", "合同金额", "总价", "计价方式"],
        "tax_rate": ["税率", "含税", "不含税"],
        "invoice": ["发票"],
        "payment_terms": ["付款", "支付"],
        "delivery_term": ["交付期限", "履行期限", "服务期限", "工期"],
        "acceptance_standard": ["验收", "检验标准", "质量标准"],
        "breach_liability": ["违约责任", "违约"],
        "termination": ["解除", "终止"],
        "confidentiality": ["保密"],
        "intellectual_property": ["知识产权"],
        "dispute_resolution": ["争议解决", "仲裁", "诉讼"],
        "signing_place": ["签署地", "签订地点"],
        "effectiveness_condition": ["生效条件", "生效"],
        "attachments": ["附件", "清单"],
    }

    def extract(self, source_task_id: str, detected_category: str, result: ContractAnalysisResult) -> ContractSchema:
        facts = {field: self._extract_field(field, result.keyFacts, result.clauses) for field in self.field_aliases}
        clauses = [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.summary,
                "page": item.page,
                "rawText": item.rawText[:1200],
                "coreLabel": item.coreLabel,
            }
            for item in result.clauses
        ]
        contract_id = f"contract_{source_task_id}"
        return ContractSchema(
            contract_id=contract_id,
            source_task_id=source_task_id,
            detected_category=detected_category,
            fields=facts,
            clauses=clauses,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    def _extract_field(self, field: str, key_facts: list[KeyFact], clauses: list[ClauseTag]) -> str | None:
        aliases = self.field_aliases[field]
        for fact in key_facts:
            if any(alias in fact.label for alias in aliases) and fact.value.strip():
                return fact.value.strip()
        for clause in clauses:
            haystack = f"{clause.title}\n{clause.summary}\n{clause.rawText}"
            if any(alias in haystack for alias in aliases):
                snippet = self._snippet(haystack, aliases)
                if snippet:
                    return snippet
        return None

    @staticmethod
    def _snippet(text: str, aliases: list[str]) -> str | None:
        for alias in aliases:
            index = text.find(alias)
            if index >= 0:
                return text[index : index + 120].strip()
        return None
