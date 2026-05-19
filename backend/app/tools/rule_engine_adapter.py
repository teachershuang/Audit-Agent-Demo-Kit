from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.schemas.contract import ClauseTag, ContractSection, KeyFact
from app.schemas.relation import AuditConfigItem, AuditConfigType


class RuleEngineAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def evaluate(
        self,
        task_id: str,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        key_facts: list[KeyFact],
        configs: list[AuditConfigItem],
    ) -> dict[str, Any]:
        rule_configs = [item for item in configs if item.enabled and item.configType == AuditConfigType.RULE_CHECK]
        if not rule_configs:
            return {"engine": "gorules", "status": "no_rule_configs", "matchedRules": [], "raw": None}
        if not self.settings.gorules_enabled or not self.settings.gorules_base_url:
            return {
                "engine": "gorules",
                "status": "not_connected",
                "matchedRules": [],
                "raw": {"message": "GoRules 未接入，当前仅生成标准化规则输入。"},
                "input": self.build_rule_input(task_id, sections, clauses, key_facts, rule_configs),
            }

        payload = self.build_rule_input(task_id, sections, clauses, key_facts, rule_configs)
        headers = {"Content-Type": "application/json"}
        if self.settings.gorules_api_key:
            headers["Authorization"] = f"Bearer {self.settings.gorules_api_key}"

        async with httpx.AsyncClient(timeout=self.settings.gorules_timeout_seconds, trust_env=False) as client:
            response = await client.post(
                f"{self.settings.gorules_base_url.rstrip('/')}{self.settings.gorules_decision_path}",
                headers=headers,
                json=payload,
            )
            if response.is_error:
                raise RuntimeError(f"GoRules API error {response.status_code}: {response.text}")
            data = response.json()

        return {
            "engine": "gorules",
            "status": "ok",
            "matchedRules": self._normalize_rule_matches(data, rule_configs),
            "raw": data,
            "input": payload,
        }

    def build_rule_input(
        self,
        task_id: str,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        key_facts: list[KeyFact],
        configs: list[AuditConfigItem],
    ) -> dict[str, Any]:
        fact_map = self._fact_map(key_facts)
        clause_map = {item.coreLabel or item.label: item for item in clauses}
        return {
            "taskId": task_id,
            "contract": {
                "contractNumber": fact_map.get("合同编号"),
                "sectionCount": len(sections),
                "clauseCount": len(clauses),
                "sections": [
                    {"id": item.id, "title": item.title, "page": item.page, "summary": item.summary}
                    for item in sections
                ],
                "clauses": [
                    {
                        "id": item.id,
                        "label": item.label,
                        "coreLabel": item.coreLabel,
                        "page": item.page,
                        "summary": item.summary,
                        "rawText": item.rawText[:1200],
                        "confidence": item.confidence,
                    }
                    for item in clauses
                ],
                "keyFacts": [
                    {
                        "id": item.id,
                        "label": item.label,
                        "value": item.value,
                        "page": item.page,
                        "confidence": item.confidence,
                    }
                    for item in key_facts
                ],
            },
            "entities": {
                "partyA": fact_map.get("甲方"),
                "partyB": fact_map.get("乙方"),
                "partySummary": fact_map.get("甲乙方信息"),
                "serviceContent": fact_map.get("服务内容"),
                "contractAmount": fact_map.get("合同金额"),
                "paymentTerms": fact_map.get("付款条件"),
                "acceptanceTerms": fact_map.get("验收标准"),
                "disputeTerms": fact_map.get("争议解决"),
                "accountInfo": fact_map.get("账户信息"),
            },
            "derived": {
                "hasContractNumber": bool(fact_map.get("合同编号") and fact_map.get("合同编号") != "未提取"),
                "hasPaymentClause": "付款条件" in clause_map,
                "hasAcceptanceClause": "验收标准" in clause_map,
                "hasBreachClause": "违约责任" in clause_map,
                "hasDisputeClause": "争议解决" in clause_map,
            },
            "auditConfigs": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "priority": item.priority.value,
                    "configType": item.configType.value,
                    "riskPrompt": item.riskPrompt,
                    "rulePayload": item.rulePayload,
                }
                for item in configs
            ],
        }

    @staticmethod
    def _fact_map(key_facts: list[KeyFact]) -> dict[str, str]:
        result: dict[str, str] = {}
        for fact in key_facts:
            if fact.label not in result and fact.value:
                result[fact.label] = fact.value
        return result

    @staticmethod
    def _normalize_rule_matches(data: dict[str, Any], configs: list[AuditConfigItem]) -> list[dict[str, Any]]:
        config_map = {item.id: item for item in configs}
        raw_matches = data.get("matchedRules") or data.get("matches") or data.get("hits") or []
        if not isinstance(raw_matches, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in raw_matches:
            if not isinstance(item, dict):
                continue
            config_id = str(item.get("configId") or item.get("id") or "").strip()
            config = config_map.get(config_id)
            normalized.append(
                {
                    "configId": config_id or None,
                    "ruleId": item.get("ruleId") or (config.rulePayload or {}).get("ruleId") if config else None,
                    "ruleName": item.get("ruleName") or item.get("name") or (config.name if config else "未命名规则"),
                    "severity": item.get("severity") or ((config.rulePayload or {}).get("severity") if config else "medium"),
                    "decision": item.get("decision") or "hit",
                    "reason": item.get("reason") or item.get("message") or (config.description if config else ""),
                    "evidenceClauseIds": item.get("evidenceClauseIds") or [],
                    "dependsOn": item.get("dependsOn") or [],
                }
            )
        return normalized
