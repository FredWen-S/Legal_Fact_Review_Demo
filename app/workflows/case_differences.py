from __future__ import annotations

from collections import defaultdict

from app.models.schemas import FieldDifference, ReviewRunDetail
from app.storage.sqlite_store import get_review_run_detail, list_review_runs
from app.utils import mask_sensitive, normalize_text


COMPARABLE_FIELDS = {
    "当事人名称",
    "统一社会信用代码",
    "法定代表人",
    "地址",
    "案号",
    "法院 / 仲裁机构名称",
    "合同编号",
    "金额",
    "日期",
    "证据编号",
    "附件编号",
}


def build_case_field_differences(case_id: str, db_path: str = "data/review_runs.sqlite") -> list[FieldDifference]:
    details: list[ReviewRunDetail] = []
    for summary in list_review_runs(case_id=case_id, path=db_path):
        detail = get_review_run_detail(summary.review_id, path=db_path)
        if detail:
            details.append(detail)
    return build_field_differences_from_reviews(details)


def build_field_differences_from_reviews(details: list[ReviewRunDetail]) -> list[FieldDifference]:
    grouped: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for detail in details:
        document_name = detail.file_name or detail.review_id
        for field in detail.external_fields:
            if field.field_type not in COMPARABLE_FIELDS:
                continue
            normalized = normalize_text(field.value)
            if not normalized:
                continue
            grouped[field.field_type][normalized].add(document_name)

    differences: list[FieldDifference] = []
    for field_type, values in grouped.items():
        if len(values) <= 1:
            continue
        all_documents = set().union(*values.values())
        if len(all_documents) <= 1:
            continue
        comparable_pairs = [
            (left, right)
            for index, left in enumerate(sorted(values))
            for right in sorted(values)[index + 1 :]
            if values[left] != values[right]
        ]
        if not comparable_pairs:
            continue
        first, second = comparable_pairs[0]
        documents = sorted(values[first] | values[second])
        differences.append(
            FieldDifference(
                field_type=field_type,
                left_value=mask_sensitive(first, field_type) or "",
                right_value=mask_sensitive(second, field_type) or "",
                documents=" / ".join(documents),
                suggested_action=f"同一案件下不同文书的“{field_type}”出现不一致，建议人工复核是否属于正常版本差异、录入错误或材料更新。",
            )
        )
    return differences
