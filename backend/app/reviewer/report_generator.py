from __future__ import annotations

from datetime import datetime

from app.schemas.review import ReviewIssue, ReviewReport


class ReportGenerator:
    def generate(
        self,
        *,
        contract_id: str,
        detected_category: str,
        matched_template: dict | None,
        issues: list[ReviewIssue],
    ) -> ReviewReport:
        severity_count = len([item for item in issues if item.severity == "must_modify"])
        summary = (
            f"识别合同类别为{detected_category}，"
            f"{'已匹配范本' if matched_template else '未匹配到有效范本'}，"
            f"共发现 {len(issues)} 个问题，其中必须修改 {severity_count} 个。"
        )
        return ReviewReport(
            contract_id=contract_id,
            status="completed",
            matched_template=None
            if matched_template is None
            else {
                "template_id": matched_template.get("template_id"),
                "template_name": matched_template.get("template_name"),
                "category_lv1": matched_template.get("category_lv1"),
                "category_lv2": matched_template.get("category_lv2"),
            },
            detected_category=detected_category,
            summary=summary,
            issues=issues,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
