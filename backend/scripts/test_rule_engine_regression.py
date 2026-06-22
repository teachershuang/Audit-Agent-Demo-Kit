from __future__ import annotations

import argparse
import asyncio
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.data.default_relations import build_default_audit_configs
from app.logging_utils import get_run_logs_dir
from app.schemas.relation import AuditConfigItem, AuditConfigType, RelationPriority, RelationToolSource
from app.tools.rule_engine_adapter import RuleEngineAdapter


def load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rule_configs() -> list[AuditConfigItem]:
    return [item for item in build_default_audit_configs() if item.configType == AuditConfigType.RULE_CHECK]


def build_missing_rule_config() -> AuditConfigItem:
    return AuditConfigItem(
        id="rule_missing_demo",
        name="不存在的规则演示",
        description="用于验证规则配置已存在，但引擎中不存在对应 ruleId 的情况。",
        enabled=True,
        riskPrompt="验证规则引擎配置失配展示。",
        toolSource=[RelationToolSource.RULE_ENGINE_FUTURE],
        priority=RelationPriority.MEDIUM,
        configType=AuditConfigType.RULE_CHECK,
        rulePayload={
            "ruleId": "rule_not_uploaded_to_engine",
            "severity": "medium",
            "extractFields": [
                {"label": "付款条件", "description": "提取付款条件用于失配测试"},
            ],
        },
    )


def build_no_hit_payload(payload: dict) -> dict:
    result = deepcopy(payload)
    result.setdefault("contract", {})["contractNumber"] = "HT-2026-001"
    result.setdefault("entities", {})["accountInfo"] = "开户名A / 开户行B / 账号123456"
    result["entities"]["contractAmount"] = "100000"
    result["derived"] = {
        "hasContractNumber": True,
        "hasPaymentClause": True,
        "hasAcceptanceClause": True,
        "hasBreachClause": True,
        "hasDisputeClause": True,
        "hasAccountClause": True,
        "crossReferences": [],
    }
    return result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", default="docs/gorules-request.example.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8999")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    payload_path = root / args.payload
    payload = load_payload(payload_path)
    rule_configs = build_rule_configs()
    missing_rule_configs = [*rule_configs, build_missing_rule_config()]
    no_hit_payload = build_no_hit_payload(payload)

    remote_settings = Settings(
        gorules_enabled=True,
        gorules_mode="remote_api",
        gorules_base_url=args.base_url,
        gorules_decision_path="/validate",
        gorules_trace_enabled=False,
    )
    broken_settings = Settings(
        gorules_enabled=True,
        gorules_mode="remote_api",
        gorules_base_url="http://127.0.0.1:8998",
        gorules_decision_path="/validate",
        gorules_trace_enabled=False,
    )

    remote_adapter = RuleEngineAdapter(remote_settings)
    broken_adapter = RuleEngineAdapter(broken_settings)

    cases = {
        "normal_match": await remote_adapter.evaluate_rule_input(payload, rule_configs, trace=False),
        "missing_rule_config": await remote_adapter.evaluate_rule_input(payload, missing_rule_configs, trace=False),
        "no_rule_hit": await remote_adapter.evaluate_rule_input(no_hit_payload, rule_configs, trace=False),
        "engine_unavailable": await broken_adapter.evaluate_rule_input(payload, rule_configs, trace=False),
    }

    summary = {
        name: {
            "status": value.get("status"),
            "matchedRules": len(value.get("matchedRules") or []),
            "missingConfiguredRules": len(value.get("missingConfiguredRules") or []),
            "unmatchedReturnedRules": len(value.get("unmatchedReturnedRules") or []),
        }
        for name, value in cases.items()
    }

    logs_dir = get_run_logs_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = logs_dir / f"rule-engine-regression-{timestamp}.json"
    output_path.write_text(
        json.dumps(
            {
                "payloadPath": str(payload_path),
                "baseUrl": args.base_url,
                "summary": summary,
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(output_path)


if __name__ == "__main__":
    asyncio.run(main())
