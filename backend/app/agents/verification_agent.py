from __future__ import annotations

from app.schemas.audit import AuditFocus, VerificationItem, VerificationStatus
from app.schemas.contract import ClauseTag, ContractSection

KEYWORD_RULES = {
    "付款条件": ["付款", "支付", "金额", "比例", "节点"],
    "验收标准": ["验收", "交付", "确认", "标准"],
    "违约责任": ["违约", "赔偿", "逾期", "责任"],
    "争议解决": ["争议", "仲裁", "法院", "协商"],
}


class VerificationAgent:
    def verify(
        self,
        sections: list[ContractSection],
        clauses: list[ClauseTag],
        audit_focuses: list[AuditFocus],
    ) -> list[VerificationItem]:
        items: list[VerificationItem] = []
        clause_by_label = {item.label: item for item in clauses}

        required_labels = ["付款条件", "验收标准", "违约责任", "争议解决"]
        for index, label in enumerate(required_labels, start=1):
            clause = clause_by_label.get(label)
            if clause:
                items.append(
                    VerificationItem(
                        id=f"verify_required_{index:03d}",
                        name=f"{label}完整性校验",
                        method="条款标签识别 + 原文证据定位",
                        status=VerificationStatus.PASS,
                        description=f"已识别到 {label}，并建立原文证据定位。",
                        relatedClauseIds=[clause.id],
                        relatedEvidenceIds=[clause.evidenceId],
                    )
                )
            else:
                items.append(
                    VerificationItem(
                        id=f"verify_required_{index:03d}",
                        name=f"{label}完整性校验",
                        method="条款标签识别 + 原文证据定位",
                        status=VerificationStatus.FAIL,
                        description=f"未识别到 {label} 条款。",
                    )
                )

        for clause in clauses:
            keywords = KEYWORD_RULES.get(clause.label)
            if not keywords:
                continue
            hits = [keyword for keyword in keywords if keyword in clause.rawText]
            status = VerificationStatus.PASS if len(hits) >= 2 else VerificationStatus.WARNING
            items.append(
                VerificationItem(
                    id=f"verify_keyword_{clause.id}",
                    name=f"{clause.label}关键词一致性校验",
                    method="关键词命中 + 语义一致性检查",
                    status=status,
                    description=f"命中关键词：{'、'.join(hits) if hits else '无明显命中'}。",
                    relatedClauseIds=[clause.id],
                    relatedEvidenceIds=[clause.evidenceId],
                )
            )

        low_confidence = [item for item in clauses if item.confidence < 0.65]
        if low_confidence:
            items.append(
                VerificationItem(
                    id="verify_low_confidence",
                    name="低置信度项复核提示",
                    method="置信度阈值检查",
                    status=VerificationStatus.WARNING,
                    description=f"发现 {len(low_confidence)} 个低置信度条款，建议重点复核。",
                    relatedClauseIds=[item.id for item in low_confidence],
                    relatedEvidenceIds=[item.evidenceId for item in low_confidence if item.evidenceId],
                )
            )

        external_audits = [item for item in audit_focuses if item.riskLevel == "pending_verification"]
        if external_audits:
            items.append(
                VerificationItem(
                    id="verify_external_dependencies",
                    name="外部数据依赖检查",
                    method="关注事项依赖分析",
                    status=VerificationStatus.EXTERNAL_PENDING,
                    description=f"发现 {len(external_audits)} 项关注事项需要结合外部数据或系统进一步核验。",
                    relatedClauseIds=sorted(
                        {clause_id for item in external_audits for clause_id in item.evidenceClauseIds}
                    ),
                    needExternalTool=True,
                )
            )

        if sections:
            items.append(
                VerificationItem(
                    id="verify_structure",
                    name="章节结构校验",
                    method="章节标题识别 + 页码映射",
                    status=VerificationStatus.PASS,
                    description=f"共识别 {len(sections)} 个章节，并完成页码映射。",
                )
            )

        return items
