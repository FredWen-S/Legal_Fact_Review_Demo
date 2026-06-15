from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.models.schemas import ExtractedReviewField, ManualReviewRecord, ReviewFinding
from app.utils import mask_sensitive


COLUMNS = {
    "severity": "风险等级",
    "risk_type": "风险类型",
    "field_name": "字段",
    "document_value": "文书值",
    "reference_value": "标准值",
    "source_location": "出现位置",
    "reference_source": "参考来源",
    "confidence": "置信度",
    "reason": "原因",
    "suggested_action": "建议动作",
}

EXTERNAL_FIELD_COLUMNS = {
    "field_type": "字段类型",
    "value": "提取值",
    "role_or_context": "角色 / 上下文",
    "source_location": "出现位置",
    "confidence": "置信度",
    "suggested_review_sources": "建议复核来源",
    "suggested_action": "建议动作",
}

MANUAL_RECORD_COLUMNS = {
    "field_type": "字段类型",
    "extracted_value": "提取值",
    "confirmed_value": "人工确认值",
    "review_status": "复核状态",
    "review_source": "复核来源",
    "reviewer_note": "复核备注",
    "source_location": "出现位置",
    "reviewed_at": "复核时间",
}


def findings_to_dataframe(findings: list[ReviewFinding]) -> pd.DataFrame:
    rows = []
    for finding in findings:
        row = finding.model_dump()
        row["document_value"] = mask_sensitive(row.get("document_value"), row.get("field_name"))
        row["reference_value"] = mask_sensitive(row.get("reference_value"), row.get("field_name"))
        rows.append({zh: row.get(en) for en, zh in COLUMNS.items()})
    return pd.DataFrame(rows, columns=list(COLUMNS.values()))


def external_fields_to_dataframe(fields: list[ExtractedReviewField]) -> pd.DataFrame:
    rows = []
    for field in fields:
        row = field.model_dump()
        row["value"] = mask_sensitive(row.get("value"), row.get("field_type"))
        row["suggested_review_sources"] = " / ".join(row.get("suggested_review_sources") or [])
        rows.append({zh: row.get(en) for en, zh in EXTERNAL_FIELD_COLUMNS.items()})
    return pd.DataFrame(rows, columns=list(EXTERNAL_FIELD_COLUMNS.values()))


def manual_records_to_dataframe(records: list[ManualReviewRecord]) -> pd.DataFrame:
    rows = []
    for record in records:
        row = record.model_dump()
        row["extracted_value"] = mask_sensitive(row.get("extracted_value"), row.get("field_type"))
        row["confirmed_value"] = mask_sensitive(row.get("confirmed_value"), row.get("field_type"))
        row["reviewed_at"] = record.reviewed_at.isoformat(timespec="seconds") if record.reviewed_at else None
        rows.append({zh: row.get(en) for en, zh in MANUAL_RECORD_COLUMNS.items()})
    return pd.DataFrame(rows, columns=list(MANUAL_RECORD_COLUMNS.values()))


def build_excel_report(
    findings: list[ReviewFinding],
    external_fields: list[ExtractedReviewField] | None = None,
    manual_records: list[ManualReviewRecord] | None = None,
    config_version: str | None = None,
    document_profile: str | None = None,
    config_updated_at: str | None = None,
) -> bytes:
    output = BytesIO()
    df = findings_to_dataframe(findings)
    external_df = external_fields_to_dataframe(external_fields or [])
    manual_df = manual_records_to_dataframe(manual_records or [])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        meta_df = pd.DataFrame(
            [
                ("规则配置版本", config_version or ""),
                ("文书类型模板", document_profile or ""),
                ("规则配置更新时间", config_updated_at or ""),
            ],
            columns=["项目", "内容"],
        )
        meta_df.to_excel(writer, index=False, sheet_name="复核元数据")
        df.to_excel(writer, index=False, sheet_name="复核发现")
        external_df.to_excel(writer, index=False, sheet_name="待外部复核字段")
        manual_df.to_excel(writer, index=False, sheet_name="人工复核记录")
        for worksheet in writer.sheets.values():
            for column_cells in worksheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 12), 42)
    return output.getvalue()
