from __future__ import annotations


def build_gorules_rule_samples() -> list[dict]:
    return [
        {
            "ruleId": "missing_contract_number",
            "name": "合同编号缺失",
            "severity": "medium",
            "when": "contract.contractNumber in [null, '', '未提取']",
            "then": {
                "decision": "hit",
                "reason": "未成功提取合同编号，建议回看首页或签署页并人工复核。",
                "dependsOn": ["合同编号"],
            },
        },
        {
            "ruleId": "payment_without_acceptance_gate",
            "name": "付款条款缺少验收约束",
            "severity": "high",
            "when": "derived.hasPaymentClause == true && derived.hasAcceptanceClause == false",
            "then": {
                "decision": "hit",
                "reason": "识别到付款条款，但未识别到明确验收标准，存在先付款后验收风险。",
                "dependsOn": ["付款条件", "验收标准"],
            },
        },
        {
            "ruleId": "missing_breach_clause",
            "name": "违约责任条款缺失",
            "severity": "medium",
            "when": "derived.hasBreachClause == false",
            "then": {
                "decision": "hit",
                "reason": "未识别到违约责任条款，建议审查合同责任约束是否完整。",
                "dependsOn": ["违约责任"],
            },
        },
        {
            "ruleId": "missing_account_info",
            "name": "账户信息缺失",
            "severity": "medium",
            "when": "entities.accountInfo in [null, '']",
            "then": {
                "decision": "hit",
                "reason": "未抽取到账户信息，若合同涉及付款执行，建议补充收款账户核验。",
                "dependsOn": ["账户信息"],
            },
        },
        {
            "ruleId": "amount_present_but_payment_missing",
            "name": "有金额无付款安排",
            "severity": "high",
            "when": "entities.contractAmount not in [null, ''] && derived.hasPaymentClause == false",
            "then": {
                "decision": "hit",
                "reason": "已识别合同金额，但未识别到付款条件，建议核查付款安排是否缺失。",
                "dependsOn": ["合同金额", "付款条件"],
            },
        },
    ]
