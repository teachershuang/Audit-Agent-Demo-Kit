from __future__ import annotations

from app.rule_engine.base import RuleHit
from app.schemas.review import ContractSchema
from app.schemas.rule import RuleRecord


class RuleRunner:
    def run(
        self,
        *,
        contract_schema: ContractSchema,
        matched_template: dict | None,
        comparison: dict,
        rules: list[RuleRecord],
    ) -> list[RuleHit]:
        hits: list[RuleHit] = []
        fields = contract_schema.fields
        for rule in rules:
            if not rule.enabled:
                continue
            logic_type = rule.logic.get("type")
            problem: str | None = None
            clause_location = ""
            if logic_type == "template_required" and matched_template is None:
                problem = rule.name
            elif logic_type == "template_category_match" and matched_template is not None:
                template_category = matched_template.get("category_lv1") or matched_template.get("category_lv2") or ""
                if contract_schema.detected_category not in template_category and template_category not in contract_schema.detected_category:
                    problem = rule.name
            elif logic_type == "schema_required":
                field_name = rule.logic.get("field")
                if not fields.get(field_name):
                    problem = rule.name
            elif logic_type == "required_any":
                field_names = rule.logic.get("fields", [])
                if not any(fields.get(field_name) for field_name in field_names):
                    problem = rule.name
            elif logic_type == "field_length_min":
                field_name = rule.logic.get("field")
                min_length = int(rule.logic.get("min_length", 0))
                value = fields.get(field_name) or ""
                if len(value) < min_length:
                    problem = rule.name
            elif logic_type == "payment_acceptance_invoice":
                payment_terms = fields.get("payment_terms") or ""
                acceptance = fields.get("acceptance_standard") or ""
                invoice = fields.get("invoice") or fields.get("tax_rate") or ""
                if payment_terms and ("验收" not in payment_terms or not acceptance or not invoice):
                    problem = rule.name
                    clause_location = "付款条款"
            elif logic_type == "prepayment":
                payment_terms = fields.get("payment_terms") or ""
                if ("预付" in payment_terms or "预付款" in payment_terms) and "验收" not in payment_terms:
                    problem = rule.name
                    clause_location = "付款条款"
            elif logic_type == "breach_equity":
                breach = fields.get("breach_liability") or ""
                if breach and ("乙方" in breach and "甲方" not in breach):
                    problem = rule.name
                    clause_location = "违约责任"
            elif logic_type == "dispute_bias":
                dispute = fields.get("dispute_resolution") or ""
                if dispute and any(keyword in dispute for keyword in ["乙方所在地", "乙方住所地", "对方所在地"]):
                    problem = rule.name
                    clause_location = "争议解决"
            elif logic_type == "reference_outdated":
                if comparison["missing"]:
                    outdated_titles = [item["title"] for item in comparison["missing"] if item["clause_type"] in {"payment", "dispute", "breach"}]
                    if outdated_titles:
                        problem = rule.name
                        clause_location = "引用条款"
            if problem:
                hits.append(
                    RuleHit(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        department=rule.department,
                        problem=problem,
                        basis_policy=rule.basis_policy,
                        basis_template=matched_template.get("template_name") if matched_template else None,
                        suggestion=rule.suggestion_template,
                        confidence=0.86,
                        clause_location=clause_location,
                    )
                )
        return hits
