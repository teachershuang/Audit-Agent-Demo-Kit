from __future__ import annotations

from app.schemas.relation import RelationConfig, RelationPriority, RelationToolSource


def build_default_relations() -> list[RelationConfig]:
    return [
        RelationConfig(
            id="relation_001",
            name="疑似内部关联交易",
            description="识别甲乙方、供应商、项目与账户信息中可能存在的关联交易线索。",
            enabled=True,
            riskPrompt="请基于合同主体、项目和账户线索判断是否存在疑似内部关联交易方向，仅输出待核验事项。",
            toolSource=[
                RelationToolSource.MODEL_INFERENCE,
                RelationToolSource.KNOWLEDGE_GRAPH_FUTURE,
                RelationToolSource.ENTERPRISE_RELATION_FUTURE,
            ],
            priority=RelationPriority.HIGH,
        ),
        RelationConfig(
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
        ),
        RelationConfig(
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
        ),
    ]
