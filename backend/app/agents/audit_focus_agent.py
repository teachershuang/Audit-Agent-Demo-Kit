from __future__ import annotations

import asyncio
import json
from typing import Any

from app.schemas.audit import AuditFocus
from app.schemas.contract import ClauseTag, ContractSection, KeyFact
from app.schemas.relation import RelationConfig
from app.services.qwen_service import QwenService


class AuditFocusAgent:
    def __init__(self, qwen_service: QwenService) -> None:
        self.qwen_service = qwen_service

    async def generate(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
    ) -> list[AuditFocus]:
        clause_map = {item.id: item for item in clauses}
        derived_focuses = self._derive_focuses_locally(clauses=clauses, relations=relations, key_facts=key_facts)
        if self._derived_focuses_are_sufficient(derived_focuses):
            return self._dedupe_audit_focuses(derived_focuses)

        if len(clauses) > 8:
            clause_groups = self._build_clause_groups(clauses, relations, key_facts)
            payloads = await asyncio.gather(
                *[
                    self._request_focus_batch(
                        sections=sections,
                        clauses=group["clauses"],
                        relations=group["relations"],
                        key_facts=group["key_facts"],
                        focus_hint=group["focus_hint"],
                    )
                    for group in clause_groups
                    if group["clauses"]
                ]
            )
            raw_items: list[dict[str, Any]] = []
            for payload in payloads:
                raw_items.extend(
                    self._pick_first_array(payload, ["auditFocuses", "\u5173\u6ce8\u4e8b\u9879", "audit_focuses"])
                )
        else:
            payload = await self._request_focus_batch(
                sections=sections,
                clauses=clauses,
                relations=relations,
                key_facts=key_facts,
                focus_hint="general",
            )
            raw_items = self._pick_first_array(payload, ["auditFocuses", "\u5173\u6ce8\u4e8b\u9879", "audit_focuses"])
        valid_clause_ids = {item.id for item in clauses}
        audit_focuses: list[AuditFocus] = []
        for index, item in enumerate(raw_items, start=1):
            clause_ids = [
                clause_id
                for clause_id in self._to_list(
                    item.get("evidenceClauseIds") or item.get("evidence_clause_ids") or item.get("\u5173\u8054\u6761\u6b3e")
                )
                if clause_id in valid_clause_ids
            ]
            if not clause_ids:
                continue

            audit_focuses.append(
                AuditFocus(
                    id=str(item.get("id") or f"audit_{index:03d}").strip(),
                    title=self._normalize_title(
                        str(item.get("title") or item.get("\u540d\u79f0") or f"Audit focus {index}").strip(),
                        clause_ids,
                        clause_map,
                        str(item.get("reason") or item.get("\u539f\u56e0") or "").strip(),
                    ),
                    riskLevel=self._normalize_risk_level(item.get("riskLevel") or item.get("\u98ce\u9669\u7b49\u7ea7")),
                    reason=str(item.get("reason") or item.get("\u539f\u56e0") or "").strip(),
                    evidenceClauseIds=clause_ids,
                    locationText=str(item.get("locationText") or item.get("\u4f4d\u7f6e") or "").strip(),
                    confidence=self._clamp_confidence(item.get("confidence") or item.get("\u7f6e\u4fe1\u5ea6") or 0.75),
                    dependsOn=self._to_list(item.get("dependsOn") or item.get("\u4f9d\u8d56\u6570\u636e")),
                    currentBasis=str(item.get("currentBasis") or item.get("\u5f53\u524d\u4f9d\u636e") or "").strip(),
                    futureTools=self._normalize_future_tools(
                        self._to_list(item.get("futureTools") or item.get("\u5efa\u8bae\u5de5\u5177")),
                        str(item.get("reason") or item.get("\u539f\u56e0") or "").strip(),
                    ),
                    modelOnly=self._to_bool(item.get("modelOnly", True)),
                    humanReviewSuggestion=str(
                        item.get("humanReviewSuggestion") or item.get("\u590d\u6838\u5efa\u8bae") or ""
                    ).strip(),
                )
            )
        return self._dedupe_audit_focuses(derived_focuses + audit_focuses)

    async def _request_focus_batch(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
        focus_hint: str,
    ) -> dict[str, Any]:
        clause_payload = [
            {
                "id": item.id,
                "label": item.label,
                "title": item.title,
                "summary": item.summary,
                "page": item.page,
                "confidence": item.confidence,
            }
            for item in clauses
        ]
        return await self.qwen_service.chat_json(
            system_prompt=(
                "You are an audit-risk analysis agent for Chinese contracts. "
                "Generate audit focus items based on sections, clauses, key facts, and relation configuration. "
                "Do not output final audit conclusions. Only output focus directions, suspected risks, or items pending verification. "
                "For related-party transactions, supplier relationships, and account anomalies, only describe them as suspected or pending external verification. "
                "Every item must include reason, evidence clause ids, location text, current basis, suggested future tools, and human review suggestion."
            ),
            user_prompt=(
                f"Focus theme: {focus_hint}\n"
                f"Sections: {json.dumps([item.model_dump() for item in sections], ensure_ascii=False)}\n"
                f"Clauses: {json.dumps(clause_payload, ensure_ascii=False)}\n"
                f"Key facts: {json.dumps([item.model_dump() for item in key_facts], ensure_ascii=False)}\n"
                f"Relation config: {json.dumps([item.model_dump() for item in relations], ensure_ascii=False)}\n"
                "Return an `auditFocuses` array. `evidenceClauseIds` must use the provided clause ids. "
                "Keep only focus items that are directly supported by the provided clauses and the theme."
            ),
            schema={"type": "object"},
            timeout=90,
        )

    @staticmethod
    def _build_clause_groups(
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
    ) -> list[dict[str, Any]]:
        base_labels = {
            "\u4ed8\u6b3e\u6761\u4ef6",
            "\u9a8c\u6536\u6807\u51c6",
            "\u8fdd\u7ea6\u8d23\u4efb",
            "\u6743\u5229\u4e49\u52a1",
            "\u4fdd\u5bc6\u6761\u6b3e",
            "\u4e89\u8bae\u89e3\u51b3",
            "\u9644\u4ef6\u6761\u6b3e",
        }
        relation_labels = {
            "\u7532\u4e59\u65b9\u4fe1\u606f",
            "\u8d26\u6237\u4fe1\u606f",
            "\u5408\u540c\u91d1\u989d",
            "\u4ed8\u6b3e\u6761\u4ef6",
            "\u5176\u4ed6\u91cd\u8981\u6761\u6b3e",
        }
        groups = []
        base_clauses = [item for item in clauses if item.label in base_labels]
        relation_clauses = [item for item in clauses if item.label in relation_labels]
        groups.append(
            {
                "focus_hint": "performance, payment, acceptance, obligation, breach",
                "clauses": base_clauses or clauses[: max(1, len(clauses) // 2)],
                "relations": [],
                "key_facts": [
                    item
                    for item in key_facts
                    if item.label
                    in {
                        "\u4ed8\u6b3e\u6761\u4ef6",
                        "\u9a8c\u6536\u6807\u51c6",
                        "\u4e89\u8bae\u89e3\u51b3",
                        "\u5408\u540c\u91d1\u989d",
                    }
                ],
            }
        )
        groups.append(
            {
                "focus_hint": "contract parties, account, supplier relationship, related-party suspicion",
                "clauses": relation_clauses or clauses[max(1, len(clauses) // 2) :],
                "relations": relations,
                "key_facts": [
                    item
                    for item in key_facts
                    if item.label
                    in {
                        "\u7532\u65b9",
                        "\u4e59\u65b9",
                        "\u8d26\u6237\u4fe1\u606f",
                        "\u5408\u540c\u91d1\u989d",
                    }
                ],
            }
        )
        return groups

    @staticmethod
    def _derive_focuses_locally(
        clauses: list[ClauseTag],
        relations: list[RelationConfig],
        key_facts: list[KeyFact],
    ) -> list[AuditFocus]:
        clause_by_label = {item.label: item for item in clauses}
        fact_labels = {item.label for item in key_facts}
        relation_names = {item.name for item in relations if item.enabled}
        focuses: list[AuditFocus] = []

        def add_focus(
            title: str,
            risk_level: str,
            reason: str,
            clause_ids: list[str],
            depends_on: list[str],
            future_tools: list[str],
            confidence: float = 0.78,
            current_basis: str = "当前基于合同文本、OCR结果和规则化语义恢复生成，仍需结合外部系统核验。",
            location_text: str = "",
            human_review_suggestion: str = "建议审计人员结合原文和业务单据进一步复核。",
        ) -> None:
            valid_clause_ids = [clause_id for clause_id in clause_ids if clause_id]
            if not valid_clause_ids:
                return
            focuses.append(
                AuditFocus(
                    id=f"audit_local_{len(focuses) + 1:03d}",
                    title=title,
                    riskLevel=AuditFocusAgent._normalize_risk_level(risk_level),
                    reason=reason,
                    evidenceClauseIds=valid_clause_ids,
                    locationText=location_text,
                    confidence=max(0.55, min(confidence, 0.95)),
                    dependsOn=depends_on,
                    currentBasis=current_basis,
                    futureTools=future_tools,
                    modelOnly=False,
                    humanReviewSuggestion=human_review_suggestion,
                )
            )

        payment_clause = clause_by_label.get("付款条件")
        acceptance_clause = clause_by_label.get("验收标准")
        if payment_clause and acceptance_clause:
            payment_text = payment_clause.rawText
            acceptance_linked = "验收" in payment_text or "验收合格" in payment_text
            add_focus(
                title="付款条件与验收闭环核验",
                risk_level="pending_verification",
                reason=(
                    "合同已识别付款条件和验收标准，但需进一步核验付款节点是否与验收完成形成严格闭环。"
                    if acceptance_linked
                    else "付款条款与验收条款同时存在，但付款节点未完全体现验收前置约束，建议重点复核。"
                ),
                clause_ids=[payment_clause.id, acceptance_clause.id],
                depends_on=["付款条件", "验收标准"],
                future_tools=["规则引擎", "付款系统", "验收单据"],
                confidence=0.82 if acceptance_linked else 0.78,
                location_text=f"第{payment_clause.page}页 / 第{acceptance_clause.page}页",
                human_review_suggestion="建议核对付款申请、验收单和节点条件是否一致。",
            )

        account_clause = clause_by_label.get("账户信息")
        if account_clause:
            add_focus(
                title="收款账户真实性核验",
                risk_level="pending_verification",
                reason="合同中存在明确收款账户信息，建议与供应商主数据、历史付款账户及开户信息做一致性核验。",
                clause_ids=[account_clause.id],
                depends_on=["账户信息"],
                future_tools=["供应商主数据", "银行账户核验", "付款系统"],
                confidence=0.84,
                location_text=f"第{account_clause.page}页",
                human_review_suggestion="建议核对开户行、账户名称、账号与付款系统留档是否一致。",
            )

        breach_clause = clause_by_label.get("违约责任")
        if breach_clause:
            add_focus(
                title="违约责任条款合理性核验",
                risk_level="medium",
                reason="已识别违约责任与赔偿表述，建议结合业务类型核验违约金比例、触发条件和责任边界是否合理。",
                clause_ids=[breach_clause.id],
                depends_on=["违约责任"],
                future_tools=["规则引擎", "法务条款库"],
                confidence=0.8,
                location_text=f"第{breach_clause.page}页",
                human_review_suggestion="建议法务或审计复核违约比例和责任触发条件。",
            )

        party_clause = clause_by_label.get("甲乙方信息")
        if party_clause:
            add_focus(
                title="合同主体与联系人一致性核验",
                risk_level="pending_verification",
                reason="合同主体、法定代表人和项目联系人已识别，建议与内部主数据、印章信息及审批资料交叉核验。",
                clause_ids=[party_clause.id],
                depends_on=["甲乙方信息", "项目联系人"],
                future_tools=["内部主数据", "合同系统", "审批流系统"],
                confidence=0.8,
                location_text=f"第{party_clause.page}页",
                human_review_suggestion="建议核对签约主体、联系人和审批留痕是否一致。",
            )

        attachment_clause = clause_by_label.get("附件条款")
        if attachment_clause:
            attachment_text = attachment_clause.rawText
            attachment_missing = "无" in attachment_text or ".*" in attachment_text
            add_focus(
                title="附件与技术文件完整性核验",
                risk_level="medium" if attachment_missing else "pending_verification",
                reason=(
                    "合同已列出技术文件/附件条款，但内容存在“无”或空缺标识，建议核验是否仍有应归档附件未纳入合同。"
                    if attachment_missing
                    else "合同存在附件或技术文件条款，建议核验附件清单、版本及签章页是否完整。"
                ),
                clause_ids=[attachment_clause.id],
                depends_on=["附件条款"],
                future_tools=["合同系统", "档案系统"],
                confidence=0.76,
                location_text=f"第{attachment_clause.page}页",
                human_review_suggestion="建议核对附件清单、技术文件版本和签章完整性。",
            )

        has_relation_focus = any(
            name in relation_names
            for name in ("疑似内部关联交易", "合同-供应商关系", "供应商-股东关系", "供应商-实际控制人关系")
        )
        if has_relation_focus and party_clause and ("甲方" in fact_labels or "乙方" in fact_labels):
            supporting_clause_ids = [party_clause.id]
            if account_clause:
                supporting_clause_ids.append(account_clause.id)
            add_focus(
                title="供应商关系与关联性核验",
                risk_level="pending_verification",
                reason="合同已识别签约主体和收款账户信息，但供应商关联关系仍需结合工商、股权和主数据进一步核验。",
                clause_ids=supporting_clause_ids,
                depends_on=["甲乙方信息", "账户信息", "供应商关系"],
                future_tools=["企业工商数据", "知识图谱", "供应商主数据"],
                confidence=0.74,
                location_text=f"第{party_clause.page}页",
                human_review_suggestion="建议结合供应商主数据和企业关系图谱复核是否存在疑似关联关系。",
            )

        service_clause = clause_by_label.get("服务/采购/工程内容")
        term_clause = clause_by_label.get("履约期限")
        if service_clause and term_clause:
            add_focus(
                title="履约范围与交付周期匹配核验",
                risk_level="pending_verification",
                reason="服务内容和履约期限均已识别，建议核验工作范围、交付周期和资源安排是否匹配。",
                clause_ids=[service_clause.id, term_clause.id],
                depends_on=["服务内容", "履约期限"],
                future_tools=["项目计划", "合同系统"],
                confidence=0.75,
                location_text=f"第{service_clause.page}页 / 第{term_clause.page}页",
                human_review_suggestion="建议结合项目计划和交付清单复核工期合理性。",
            )

        return focuses

    @staticmethod
    def _derived_focuses_are_sufficient(items: list[AuditFocus]) -> bool:
        if len(items) < 5:
            return False
        titles = {item.title for item in items}
        return len(titles) >= 5

    @staticmethod
    def _dedupe_audit_focuses(items: list[AuditFocus]) -> list[AuditFocus]:
        best_by_key: dict[tuple[str, tuple[str, ...]], AuditFocus] = {}
        for item in items:
            key = (item.title, tuple(sorted(item.evidenceClauseIds)))
            current = best_by_key.get(key)
            if current is None or item.confidence > current.confidence:
                best_by_key[key] = item
        deduped = list(best_by_key.values())
        deduped.sort(key=lambda item: (-item.confidence, item.title))
        for index, item in enumerate(deduped, start=1):
            item.id = f"audit_{index:03d}"
        return deduped

    @staticmethod
    def _pick_first_array(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            normalized = value.replace("\uff1b", "\u3002").replace(";", "\u3002").replace("\u3001", "\u3002")
            return [part.strip() for part in normalized.split("\u3002") if part.strip()]
        return []

    @staticmethod
    def _normalize_risk_level(value: Any) -> str:
        mapping = {
            "\u4f4e": "low",
            "\u4e2d": "medium",
            "\u9ad8": "high",
            "\u5f85\u6838\u9a8c": "pending_verification",
            "pending": "pending_verification",
            "pending_verification": "pending_verification",
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        return mapping.get(str(value or "pending_verification").strip(), "pending_verification")

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.5
        return max(0.01, min(score, 0.99))

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "\u5426"}
        return bool(value)

    @staticmethod
    def _normalize_title(
        title: str,
        clause_ids: list[str],
        clause_map: dict[str, ClauseTag],
        reason: str,
    ) -> str:
        normalized = title.strip()
        if normalized and not normalized.lower().startswith("audit focus "):
            return normalized

        labels = {clause_map[clause_id].label for clause_id in clause_ids if clause_id in clause_map}
        if "\u4ed8\u6b3e\u6761\u4ef6" in labels or "\u9a8c\u6536\u6807\u51c6" in labels:
            return "\u4ed8\u6b3e\u6761\u4ef6\u4e0e\u9a8c\u6536\u95ed\u73af\u6838\u9a8c"
        if "\u8fdd\u7ea6\u8d23\u4efb" in labels and "\u4fdd\u5bc6\u6761\u6b3e" in labels:
            return "\u4fdd\u5bc6\u4e49\u52a1\u4e0e\u8fdd\u7ea6\u8d23\u4efb\u4e00\u81f4\u6027\u6838\u9a8c"
        if "\u8fdd\u7ea6\u8d23\u4efb" in labels:
            return "\u8fdd\u7ea6\u8d23\u4efb\u6761\u6b3e\u5408\u7406\u6027\u6838\u9a8c"
        if "\u8d26\u6237\u4fe1\u606f" in labels:
            return "\u6536\u6b3e\u8d26\u6237\u771f\u5b9e\u6027\u6838\u9a8c"
        if "\u7532\u4e59\u65b9\u4fe1\u606f" in labels:
            return "\u5408\u540c\u4e3b\u4f53\u4e0e\u8054\u7cfb\u4eba\u4e00\u81f4\u6027\u6838\u9a8c"
        if any(keyword in reason for keyword in ("\u5173\u8054", "\u4f9b\u5e94\u5546", "\u80a1\u4e1c", "\u5b9e\u63a7")):
            return "\u4f9b\u5e94\u5546\u5173\u7cfb\u4e0e\u5173\u8054\u6027\u6838\u9a8c"
        return "\u5ba1\u8ba1\u5173\u6ce8\u4e8b\u9879"

    @staticmethod
    def _normalize_future_tools(current: list[str], reason: str) -> list[str]:
        if current:
            return current
        if any(keyword in reason for keyword in ("\u5173\u8054", "\u4f9b\u5e94\u5546", "\u80a1\u4e1c", "\u5b9e\u63a7")):
            return ["\u4f01\u4e1a\u5de5\u5546\u6570\u636e", "\u77e5\u8bc6\u56fe\u8c31", "\u4f9b\u5e94\u5546\u4e3b\u6570\u636e"]
        if any(keyword in reason for keyword in ("\u8d26\u6237", "\u94f6\u884c", "\u6536\u6b3e")):
            return ["\u94f6\u884c\u8d26\u6237\u6838\u9a8c", "\u4f9b\u5e94\u5546\u4e3b\u6570\u636e"]
        return ["\u89c4\u5219\u5f15\u64ce", "\u77e5\u8bc6\u56fe\u8c31"]
