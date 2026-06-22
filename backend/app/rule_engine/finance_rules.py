from __future__ import annotations


FINANCE_RULES = [
    {
        "id": "RULE_011",
        "name": "缺少价款或计价方式",
        "severity": "must_modify",
        "department": "finance",
        "keywords": ["价款", "计价"],
        "logic": {"type": "schema_required", "field": "price"},
        "suggestion_template": "请补充价款金额或计价方式。",
    },
    {
        "id": "RULE_012",
        "name": "缺少含税/不含税/税率约定",
        "severity": "suggest_modify",
        "department": "finance",
        "keywords": ["税率", "含税", "不含税"],
        "logic": {"type": "schema_required", "field": "tax_rate"},
        "suggestion_template": "建议明确含税/不含税口径和适用税率。",
    },
    {
        "id": "RULE_013",
        "name": "缺少发票要求",
        "severity": "suggest_modify",
        "department": "finance",
        "keywords": ["发票"],
        "logic": {"type": "schema_required", "field": "invoice"},
        "suggestion_template": "建议补充发票类型、税率和开票要求。",
    },
    {
        "id": "RULE_014",
        "name": "付款条件未绑定验收和发票",
        "severity": "must_modify",
        "department": "finance",
        "keywords": ["付款", "验收", "发票"],
        "logic": {"type": "payment_acceptance_invoice"},
        "suggestion_template": "请将付款条件与验收完成、发票开具等前提绑定。",
    },
    {
        "id": "RULE_015",
        "name": "存在无条件全额预付款",
        "severity": "must_modify",
        "department": "finance",
        "keywords": ["预付款", "支付"],
        "logic": {"type": "prepayment"},
        "suggestion_template": "请取消或限制无条件全额预付款安排。",
    },
]
