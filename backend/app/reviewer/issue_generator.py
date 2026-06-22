from __future__ import annotations

from uuid import uuid4

from app.rule_engine.base import RuleHit
from app.schemas.review import ContractSchema, ReviewIssue


class IssueGenerator:
    field_title_map = {
        "合同编号": "contract_number",
        "协议编号": "contract_number",
        "合同主体": "contract_parties",
        "统一社会信用代码": "unified_social_credit_code",
        "法定代表人": "legal_representative",
        "授权代表": "legal_representative",
        "合同标的": "contract_subject",
        "服务内容": "contract_subject",
        "数量": "quantity",
        "质量": "quality",
        "规格": "quality",
        "价款": "price",
        "合同金额": "price",
        "税率": "tax_rate",
        "发票": "invoice",
        "付款": "payment_terms",
        "支付": "payment_terms",
        "履行期限": "delivery_term",
        "交付期限": "delivery_term",
        "验收标准": "acceptance_standard",
        "违约责任": "breach_liability",
        "争议解决": "dispute_resolution",
        "生效条件": "effectiveness_condition",
    }

    def generate(
        self,
        *,
        comparison: dict,
        rule_hits: list[RuleHit],
        matched_template: dict | None,
        contract_schema: ContractSchema,
        policy_lookup: callable,
        template_detail_builder: callable,
    ) -> list[ReviewIssue]:
        issues: list[ReviewIssue] = []
        seen_keys: set[tuple[str, str, str]] = set()

        if matched_template is not None:
            for item in comparison["missing"]:
                if self._should_skip_missing(item["title"], contract_schema):
                    continue
                dedupe_key = ("template_missing", "must_modify", item["title"].strip())
                if dedupe_key in seen_keys:
                    continue
                basis_details = policy_lookup(item["title"], return_details=True)
                issues.append(
                    ReviewIssue(
                        id=f"issue_{uuid4().hex[:10]}",
                        severity="must_modify",
                        department="legal",
                        clause_location=f"范本条款: {item['title']}",
                        problem=f"待审合同缺少范本关键条款：{item['title']}",
                        basis_policy=self._basis_titles(basis_details),
                        basis_policy_details=basis_details,
                        basis_template=matched_template.get("template_name"),
                        basis_template_detail=template_detail_builder(matched_template, item["title"]),
                        suggestion=f"请补充或引用与范本一致的“{item['title']}”条款。",
                        confidence=0.84,
                        extra={
                            "source": "template_missing",
                            "template_clause_id": item["template_clause_id"],
                            "no_direct_evidence": True,
                        },
                    )
                )
                seen_keys.add(dedupe_key)

            for item in comparison["weakened"]:
                dedupe_key = ("template_weakened", "suggest_modify", item["title"].strip())
                if dedupe_key in seen_keys:
                    continue
                basis_details = policy_lookup(item["title"], return_details=True)
                issues.append(
                    ReviewIssue(
                        id=f"issue_{uuid4().hex[:10]}",
                        severity="suggest_modify",
                        department="business",
                        clause_location=f"条款比对: {item['title']}",
                        problem=f"待审合同对应条款相较范本存在弱化或偏差：{item['title']}",
                        basis_policy=self._basis_titles(basis_details),
                        basis_policy_details=basis_details,
                        basis_template=matched_template.get("template_name"),
                        basis_template_detail=template_detail_builder(matched_template, item["title"]),
                        suggestion=f"请核对“{item['title']}”条款表述，避免责任或条件被弱化。",
                        confidence=0.76,
                        extra={"source": "template_weakened", "score": item["score"]},
                    )
                )
                seen_keys.add(dedupe_key)

        for hit in rule_hits:
            dedupe_key = ("rule", hit.severity, hit.problem.strip())
            if dedupe_key in seen_keys:
                continue
            basis_details = policy_lookup(hit.problem, clause_ids=hit.basis_policy, return_details=True)
            issues.append(
                ReviewIssue(
                    id=f"issue_{uuid4().hex[:10]}",
                    severity=hit.severity,
                    department=hit.department,
                    clause_location=hit.clause_location,
                    problem=hit.problem,
                    basis_policy=self._basis_titles(basis_details),
                    basis_policy_details=basis_details,
                    basis_template=hit.basis_template,
                    basis_template_detail=template_detail_builder(matched_template, hit.problem),
                    source_rule_id=hit.rule_id,
                    source_rule_name=hit.rule_name,
                    suggestion=hit.suggestion,
                    confidence=hit.confidence,
                    extra={
                        "source": "rule",
                        "rule_id": hit.rule_id,
                        "no_direct_evidence": self._rule_has_no_direct_evidence(hit),
                    },
                )
            )
            seen_keys.add(dedupe_key)
        return issues

    @classmethod
    def _should_skip_missing(cls, title: str, contract_schema: ContractSchema) -> bool:
        normalized = title.replace("：", "").replace(":", "").strip()
        for prefix, field_name in cls.field_title_map.items():
            if normalized.startswith(prefix) and contract_schema.fields.get(field_name):
                return True
        return False

    @staticmethod
    def _basis_titles(basis_details: list[dict]) -> list[str]:
        titles = []
        for item in basis_details:
            title = str(item.get("title") or "").strip()
            if title and title not in titles:
                titles.append(title)
        return titles

    @staticmethod
    def _rule_has_no_direct_evidence(hit: RuleHit) -> bool:
        if hit.clause_location.strip():
            return False
        keywords = ["缺少", "未匹配到有效集团范本", "类型不一致", "引用废止制度", "旧范本"]
        return any(keyword in hit.problem for keyword in keywords)
