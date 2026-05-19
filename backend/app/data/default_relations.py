from __future__ import annotations

from app.schemas.relation import AuditConfigItem, AuditConfigType, RelationConfig, RelationPriority, RelationToolSource


def build_default_audit_configs() -> list[AuditConfigItem]:
    return [
        AuditConfigItem(
            id="relation_001",
            name="疑似内部关联交易核验",
            description="识别甲乙方、供应商、项目与账户信息中可能存在的关联交易线索。",
            enabled=True,
            riskPrompt="请基于合同主体、项目和账户线索判断是否存在疑似内部关联交易方向，仅输出待核验事项。",
            toolSource=[
                RelationToolSource.MODEL_INFERENCE,
                RelationToolSource.KNOWLEDGE_GRAPH_FUTURE,
                RelationToolSource.ENTERPRISE_RELATION_FUTURE,
            ],
            priority=RelationPriority.HIGH,
            configType=AuditConfigType.RELATION_FOCUS,
        ),
        AuditConfigItem(
            id="relation_002",
            name="合同-付款节点关系",
            description="分析合同金额、付款比例与验收节点是否匹配。",
            enabled=True,
            riskPrompt="关注付款比例、付款触发条件与验收条款之间是否存在前置付款风险。",
            toolSource=[
                RelationToolSource.MODEL_INFERENCE,
                RelationToolSource.RULE_ENGINE_FUTURE,
                RelationToolSource.RPA_API_FUTURE,
            ],
            priority=RelationPriority.HIGH,
            configType=AuditConfigType.RELATION_FOCUS,
        ),
        AuditConfigItem(
            id="relation_003",
            name="供应商关系待核验",
            description="检查供应商名称、股东、法人和账户信息是否需要外部关系库核验。",
            enabled=True,
            riskPrompt="如合同文本出现集团内部名称相似性或账户异常，请提示需要接入主数据与企业关系库。",
            toolSource=[
                RelationToolSource.MODEL_INFERENCE,
                RelationToolSource.ENTERPRISE_RELATION_FUTURE,
                RelationToolSource.INTERNAL_MASTER_DATA_FUTURE,
            ],
            priority=RelationPriority.MEDIUM,
            configType=AuditConfigType.EXTERNAL_CHECK,
        ),
        AuditConfigItem(
            id="rule_001",
            name="付款条款缺少验收约束",
            description="当存在付款条款但未看到明确验收后付款约束时触发。",
            enabled=True,
            riskPrompt="识别付款是否与验收闭环脱节，提示先付款后验收风险。",
            toolSource=[RelationToolSource.RULE_ENGINE_FUTURE, RelationToolSource.MODEL_INFERENCE],
            priority=RelationPriority.HIGH,
            configType=AuditConfigType.RULE_CHECK,
            rulePayload={
                "ruleId": "payment_without_acceptance_gate",
                "severity": "high",
                "expectedClauses": ["付款条件", "验收标准"],
                "extractFields": [
                    {"label": "付款条件", "description": "提取付款触发条件、比例和节点"},
                    {"label": "验收标准", "description": "提取验收是否作为付款前置条件"},
                ],
                "expressionHint": "payment_clause_exists && !acceptance_clause_mentions_payment_gate",
            },
        ),
        AuditConfigItem(
            id="rule_002",
            name="合同编号缺失",
            description="当合同编号未成功抽取时触发。",
            enabled=True,
            riskPrompt="检查合同首页是否存在合同编号或协议编号，缺失时提示人工复核。",
            toolSource=[RelationToolSource.RULE_ENGINE_FUTURE, RelationToolSource.MODEL_INFERENCE],
            priority=RelationPriority.MEDIUM,
            configType=AuditConfigType.RULE_CHECK,
            rulePayload={
                "ruleId": "missing_contract_number",
                "severity": "medium",
                "expectedFacts": ["合同编号"],
                "extractFields": [
                    {"label": "合同编号", "description": "仅提取合同编号本身，不要返回合同名称"},
                ],
                "expressionHint": "contract_number in [null, '', '未提取']",
            },
        ),
        AuditConfigItem(
            id="rule_003",
            name="违约责任条款缺失",
            description="当合同中未识别到违约责任条款时触发。",
            enabled=True,
            riskPrompt="检查合同是否设置了违约责任和赔偿约束，缺失时给出提示。",
            toolSource=[RelationToolSource.RULE_ENGINE_FUTURE, RelationToolSource.MODEL_INFERENCE],
            priority=RelationPriority.MEDIUM,
            configType=AuditConfigType.RULE_CHECK,
            rulePayload={
                "ruleId": "missing_breach_clause",
                "severity": "medium",
                "expectedClauses": ["违约责任"],
                "extractFields": [
                    {"label": "违约责任", "description": "提取违约责任、赔偿约束和逾期责任"},
                ],
                "expressionHint": "!breach_clause_exists",
            },
        ),
        AuditConfigItem(
            id="rule_004",
            name="账户信息缺失",
            description="当合同中未识别到账户信息时触发。",
            enabled=True,
            riskPrompt="检查合同是否提供了收款账户信息，缺失时提示付款执行风险。",
            toolSource=[RelationToolSource.RULE_ENGINE_FUTURE, RelationToolSource.MODEL_INFERENCE],
            priority=RelationPriority.MEDIUM,
            configType=AuditConfigType.RULE_CHECK,
            rulePayload={
                "ruleId": "missing_account_info",
                "severity": "medium",
                "expectedFacts": ["账户信息"],
                "extractFields": [
                    {"label": "账户信息", "description": "提取开户名、开户行、账号等账户字段"},
                ],
                "expressionHint": "account_info in [null, '']",
            },
        ),
        AuditConfigItem(
            id="rule_005",
            name="有金额但缺少付款安排",
            description="当已识别合同金额但未识别付款条款时触发。",
            enabled=True,
            riskPrompt="检查合同是否存在金额约定但未写明付款安排，提示履约结算风险。",
            toolSource=[RelationToolSource.RULE_ENGINE_FUTURE, RelationToolSource.MODEL_INFERENCE],
            priority=RelationPriority.HIGH,
            configType=AuditConfigType.RULE_CHECK,
            rulePayload={
                "ruleId": "amount_present_but_payment_missing",
                "severity": "high",
                "expectedFacts": ["合同金额", "付款条件"],
                "extractFields": [
                    {"label": "合同金额", "description": "提取合同总金额、含税金额或价税合计"},
                    {"label": "付款条件", "description": "提取付款节点、付款比例和支付方式"},
                ],
                "expressionHint": "contract_amount_exists && !payment_clause_exists",
            },
        ),
    ]


def build_default_relations() -> list[RelationConfig]:
    return [RelationConfig.model_validate(item.model_dump()) for item in build_default_audit_configs()]
