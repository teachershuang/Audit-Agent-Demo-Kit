from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.logging_utils import app_logger, get_run_logs_dir, json_dumps
from app.schemas.contract import ClauseTag, ContractSection, KeyFact
from app.schemas.relation import AuditConfigItem, AuditConfigType


class RuleEngineAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._zen_engine = None
        self._zen_decision = None
        self._zen_decision_mtime_ns: int | None = None
        self._root_dir = Path(__file__).resolve().parents[2]

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
            return {
                "engine": "gorules",
                "status": "no_rule_configs",
                "matchedRules": [],
                "configuredRules": [],
                "availableRuleIds": [],
                "missingConfiguredRules": [],
                "unmatchedReturnedRules": [],
                "raw": None,
                "input": None,
            }

        payload = self.build_rule_input(task_id, sections, clauses, key_facts, rule_configs)
        return await self.evaluate_rule_input(payload, rule_configs)

    async def evaluate_rule_input(
        self,
        payload: dict[str, Any],
        configs: list[AuditConfigItem],
        trace: bool | None = None,
    ) -> dict[str, Any]:
        trace_flag = self.settings.gorules_trace_enabled if trace is None else trace
        mode = (self.settings.gorules_mode or "remote_api").strip().lower()
        configured_rules = self._serialize_configured_rules(configs)

        try:
            available_rule_ids = await self._get_available_rule_ids(mode)
        except Exception as exc:
            app_logger.warning(
                json_dumps(
                    {
                        "event": "gorules_rules_catalog_failed",
                        "mode": mode,
                        "error": str(exc),
                    }
                )
            )
            available_rule_ids = []

        missing_configured_rules = self._find_missing_configured_rules(configs, available_rule_ids)

        if mode == "local_zen":
            try:
                data = await self._evaluate_local(payload, trace_flag)
                result_payload = self._extract_result_payload(data)
                matched_rules = self._normalize_rule_matches(result_payload, configs)
                unmatched_returned_rules = self._find_unmatched_returned_rules(matched_rules, configs)
                result = self._build_result(
                    mode="local_zen",
                    status="ok_with_warnings" if (missing_configured_rules or unmatched_returned_rules) else "ok",
                    payload=payload,
                    raw=data,
                    configured_rules=configured_rules,
                    available_rule_ids=available_rule_ids,
                    missing_configured_rules=missing_configured_rules,
                    unmatched_returned_rules=unmatched_returned_rules,
                    matched_rules=matched_rules,
                )
                self._log_runtime_pair("local_zen", payload, result)
                return result
            except Exception as exc:
                result = self._build_result(
                    mode="local_zen",
                    status="engine_error",
                    payload=payload,
                    raw={"message": str(exc)},
                    configured_rules=configured_rules,
                    available_rule_ids=available_rule_ids,
                    missing_configured_rules=missing_configured_rules,
                    unmatched_returned_rules=[],
                    matched_rules=[],
                )
                self._log_runtime_pair("local_zen", payload, result)
                return result

        if not self.settings.gorules_enabled or not self.settings.gorules_base_url:
            result = self._build_result(
                mode=mode,
                status="not_connected",
                payload=payload,
                raw={"message": "GoRules 未接入，当前仅生成标准化规则输入。"},
                configured_rules=configured_rules,
                available_rule_ids=available_rule_ids,
                missing_configured_rules=missing_configured_rules,
                unmatched_returned_rules=[],
                matched_rules=[],
            )
            self._log_runtime_pair(mode, payload, result)
            return result

        headers = {"Content-Type": "application/json"}
        if self.settings.gorules_api_key:
            headers["X-Access-Token"] = self.settings.gorules_api_key

        request_body = (
            {"payload": payload, "trace": trace_flag}
            if self.settings.gorules_decision_path.rstrip("/").endswith("/validate")
            else {"context": payload, "trace": trace_flag}
        )

        try:
            async with httpx.AsyncClient(timeout=self.settings.gorules_timeout_seconds, trust_env=False) as client:
                response = await client.post(
                    f"{self.settings.gorules_base_url.rstrip('/')}{self.settings.gorules_decision_path}",
                    headers=headers,
                    json=request_body,
                )
                if response.is_error:
                    raise RuntimeError(f"GoRules API error {response.status_code}: {response.text}")
                data = response.json()

            result_payload = self._extract_result_payload(data)
            matched_rules = self._normalize_rule_matches(result_payload, configs)
            unmatched_returned_rules = self._find_unmatched_returned_rules(matched_rules, configs)
            result = self._build_result(
                mode="remote_api",
                status="ok_with_warnings" if (missing_configured_rules or unmatched_returned_rules) else "ok",
                payload=payload,
                raw=data,
                configured_rules=configured_rules,
                available_rule_ids=available_rule_ids,
                missing_configured_rules=missing_configured_rules,
                unmatched_returned_rules=unmatched_returned_rules,
                matched_rules=matched_rules,
            )
            self._log_runtime_pair("remote_api", request_body, result)
            return result
        except Exception as exc:
            result = self._build_result(
                mode="remote_api",
                status="engine_error",
                payload=payload,
                raw={"message": str(exc)},
                configured_rules=configured_rules,
                available_rule_ids=available_rule_ids,
                missing_configured_rules=missing_configured_rules,
                unmatched_returned_rules=[],
                matched_rules=[],
            )
            self._log_runtime_pair("remote_api", request_body, result)
            return result

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
                "contractNumber": self._normalize_missing_value(fact_map.get("合同编号")),
                "sectionCount": len(sections),
                "clauseCount": len(clauses),
                "sections": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "level": item.level,
                        "page": item.page,
                        "sortOrder": item.sortOrder,
                        "sectionCode": item.sectionCode,
                        "sectionPath": item.sectionPath,
                        "summary": item.summary,
                    }
                    for item in sections
                ],
                "clauses": [
                    {
                        "id": item.id,
                        "label": item.label,
                        "coreLabel": item.coreLabel,
                        "labelSource": item.labelSource,
                        "title": item.title,
                        "sectionTitle": item.sectionTitle,
                        "page": item.page,
                        "sortOrder": item.sortOrder,
                        "summary": item.summary,
                        "rawText": item.rawText[:1200],
                        "references": item.references,
                        "structuredFields": item.structuredFields,
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
                "partyA": self._normalize_missing_value(fact_map.get("甲方")),
                "partyB": self._normalize_missing_value(fact_map.get("乙方")),
                "partySummary": self._normalize_missing_value(fact_map.get("甲乙方信息")),
                "subjectSummary": self._normalize_missing_value(fact_map.get("主体摘要")),
                "serviceContent": self._normalize_missing_value(fact_map.get("服务内容")),
                "contractAmount": self._normalize_missing_value(fact_map.get("合同金额")),
                "paymentTerms": self._normalize_missing_value(fact_map.get("付款条件")),
                "acceptanceTerms": self._normalize_missing_value(fact_map.get("验收标准")),
                "performanceTerm": self._normalize_missing_value(fact_map.get("履约期限")),
                "disputeTerms": self._normalize_missing_value(fact_map.get("争议解决")),
                "accountInfo": self._normalize_missing_value(fact_map.get("账户信息")),
            },
            "factMap": {
                key: value for key, value in fact_map.items() if self._normalize_missing_value(value) is not None
            },
            "derived": {
                "hasContractNumber": bool(self._normalize_missing_value(fact_map.get("合同编号"))),
                "hasPaymentClause": "付款条件" in clause_map,
                "hasAcceptanceClause": "验收标准" in clause_map,
                "hasBreachClause": "违约责任" in clause_map,
                "hasDisputeClause": "争议解决" in clause_map,
                "hasAccountClause": "账户信息" in clause_map,
                "crossReferences": self._collect_cross_references(clauses),
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

    async def _evaluate_local(self, payload: dict[str, Any], trace: bool) -> dict[str, Any]:
        decision = self._load_local_decision()
        return await asyncio.to_thread(decision.evaluate, payload, {"trace": trace})

    def _load_local_decision(self):
        try:
            import zen
        except ImportError as exc:
            raise RuntimeError("本地规则执行依赖 zen-engine，但当前环境未安装。") from exc

        decision_path = Path(self.settings.gorules_local_decision_file)
        if not decision_path.is_absolute():
            decision_path = self._root_dir / decision_path
        if not decision_path.exists():
            raise RuntimeError(f"本地规则决策文件不存在: {decision_path}")

        stat = decision_path.stat()
        if self._zen_decision is None or self._zen_decision_mtime_ns != stat.st_mtime_ns:
            self._zen_engine = zen.ZenEngine()
            self._zen_decision = self._zen_engine.create_decision(decision_path.read_text(encoding="utf-8"))
            self._zen_decision_mtime_ns = stat.st_mtime_ns
        return self._zen_decision

    async def _get_available_rule_ids(self, mode: str) -> list[str]:
        if mode == "local_zen":
            return self._read_local_rule_ids()

        if not self.settings.gorules_enabled or not self.settings.gorules_base_url:
            return []

        rules_url = f"{self.settings.gorules_base_url.rstrip('/')}/rules"
        async with httpx.AsyncClient(timeout=self.settings.gorules_timeout_seconds, trust_env=False) as client:
            response = await client.get(rules_url)
            if response.is_error:
                raise RuntimeError(f"GoRules rules API error {response.status_code}: {response.text}")
            data = response.json()

        rules = data.get("rules", [])
        if not isinstance(rules, list):
            return []

        rule_ids: list[str] = []
        for item in rules:
            if not isinstance(item, dict):
                continue
            rule_id = self._unquote_string(item.get("output_rule_id"))
            if rule_id:
                rule_ids.append(rule_id)
        return sorted(set(rule_ids))

    def _read_local_rule_ids(self) -> list[str]:
        decision_path = Path(self.settings.gorules_local_decision_file)
        if not decision_path.is_absolute():
            decision_path = self._root_dir / decision_path
        if not decision_path.exists():
            return []

        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        rule_ids: list[str] = []
        for node in decision.get("nodes", []):
            content = node.get("content") if isinstance(node, dict) else None
            if not isinstance(content, dict):
                continue
            for rule in content.get("rules", []):
                if not isinstance(rule, dict):
                    continue
                rule_id = self._unquote_string(rule.get("output_rule_id"))
                if rule_id:
                    rule_ids.append(rule_id)
        return sorted(set(rule_ids))

    @staticmethod
    def _extract_result_payload(data: dict[str, Any]) -> dict[str, Any]:
        result = data.get("result", data)
        if isinstance(result, dict):
            if isinstance(result.get("matchedRules"), list):
                return result
            return {"matchedRules": result.get("matches") or result.get("hits") or []}
        if isinstance(result, list):
            return {"matchedRules": result}
        return {"matchedRules": []}

    @staticmethod
    def _fact_map(key_facts: list[KeyFact]) -> dict[str, str]:
        result: dict[str, str] = {}
        for fact in key_facts:
            if fact.label not in result and fact.value:
                result[fact.label] = fact.value
        return result

    @staticmethod
    def _normalize_missing_value(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned or cleaned in {"未提取", "待提取"}:
            return None
        return cleaned

    @staticmethod
    def _collect_cross_references(clauses: list[ClauseTag]) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for clause in clauses:
            if not clause.references:
                continue
            references.append(
                {
                    "clauseId": clause.id,
                    "label": clause.label,
                    "page": clause.page,
                    "references": clause.references,
                }
            )
        return references

    @staticmethod
    def _serialize_configured_rules(configs: list[AuditConfigItem]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for config in configs:
            rule_payload = config.rulePayload if isinstance(config.rulePayload, dict) else {}
            serialized.append(
                {
                    "configId": config.id,
                    "name": config.name,
                    "ruleId": str(rule_payload.get("ruleId") or "").strip() or None,
                    "severity": rule_payload.get("severity"),
                    "extractFields": rule_payload.get("extractFields") or [],
                }
            )
        return serialized

    @staticmethod
    def _find_missing_configured_rules(
        configs: list[AuditConfigItem],
        available_rule_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not available_rule_ids:
            return []
        available = set(available_rule_ids)
        missing: list[dict[str, Any]] = []
        for config in configs:
            rule_payload = config.rulePayload if isinstance(config.rulePayload, dict) else {}
            rule_id = str(rule_payload.get("ruleId") or "").strip()
            if rule_id and rule_id not in available:
                missing.append(
                    {
                        "configId": config.id,
                        "name": config.name,
                        "ruleId": rule_id,
                    }
                )
        return missing

    @staticmethod
    def _find_unmatched_returned_rules(
        matched_rules: list[dict[str, Any]],
        configs: list[AuditConfigItem],
    ) -> list[dict[str, Any]]:
        config_ids = {item.id for item in configs}
        rule_ids = {
            str(item.rulePayload.get("ruleId") or "").strip()
            for item in configs
            if isinstance(item.rulePayload, dict)
        }
        unmatched: list[dict[str, Any]] = []
        for item in matched_rules:
            config_id = str(item.get("configId") or "").strip()
            rule_id = str(item.get("ruleId") or "").strip()
            if config_id and config_id in config_ids:
                continue
            if rule_id and rule_id in rule_ids:
                continue
            unmatched.append(
                {
                    "configId": config_id or None,
                    "ruleId": rule_id or None,
                    "ruleName": item.get("ruleName"),
                }
            )
        return unmatched

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
            rule_id = str(item.get("ruleId") or "").strip()
            config = config_map.get(config_id)
            if config is None and rule_id:
                config = next(
                    (
                        candidate
                        for candidate in configs
                        if isinstance(candidate.rulePayload, dict)
                        and str(candidate.rulePayload.get("ruleId") or "").strip() == rule_id
                    ),
                    None,
                )
            rule_payload = config.rulePayload if config and isinstance(config.rulePayload, dict) else {}
            normalized.append(
                {
                    "configId": config_id or (config.id if config else None),
                    "ruleId": rule_id or rule_payload.get("ruleId"),
                    "ruleName": item.get("ruleName") or item.get("name") or (config.name if config else "未命名规则"),
                    "severity": item.get("severity") or rule_payload.get("severity") or "medium",
                    "decision": item.get("decision") or "hit",
                    "reason": item.get("reason") or item.get("message") or (config.description if config else ""),
                    "evidenceClauseIds": item.get("evidenceClauseIds") or [],
                    "dependsOn": item.get("dependsOn") or [],
                }
            )
        return normalized

    @staticmethod
    def _unquote_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text or None

    def _build_result(
        self,
        *,
        mode: str,
        status: str,
        payload: dict[str, Any] | None,
        raw: Any,
        configured_rules: list[dict[str, Any]],
        available_rule_ids: list[str],
        missing_configured_rules: list[dict[str, Any]],
        unmatched_returned_rules: list[dict[str, Any]],
        matched_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "engine": "gorules",
            "mode": mode,
            "status": status,
            "matchedRules": matched_rules,
            "configuredRules": configured_rules,
            "availableRuleIds": available_rule_ids,
            "missingConfiguredRules": missing_configured_rules,
            "unmatchedReturnedRules": unmatched_returned_rules,
            "raw": raw,
            "input": payload,
        }

    def _log_runtime_pair(self, mode: str, request_payload: Any, response_payload: Any) -> None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        logs_dir = get_run_logs_dir() / "gorules-runtime"
        logs_dir.mkdir(parents=True, exist_ok=True)
        request_path = logs_dir / f"{timestamp}-{mode}.request.json"
        response_path = logs_dir / f"{timestamp}-{mode}.response.json"
        request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        response_path.write_text(json.dumps(response_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        app_logger.info(
            json_dumps(
                {
                    "event": "gorules_runtime_logged",
                    "mode": mode,
                    "requestLog": str(request_path),
                    "responseLog": str(response_path),
                    "status": response_payload.get("status"),
                    "matchedRuleCount": len(response_payload.get("matchedRules") or []),
                    "missingConfiguredRuleCount": len(response_payload.get("missingConfiguredRules") or []),
                }
            )
        )
