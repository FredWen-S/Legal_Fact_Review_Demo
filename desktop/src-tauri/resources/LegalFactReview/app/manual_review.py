from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd

from app.models.schemas import ExtractedReviewField, ManualReviewRecord
from app.utils import stable_id


REVIEW_STATUSES = ["未复核", "已确认", "需修改", "已忽略"]
DEFAULT_REVIEW_SOURCES = [
    "企查查",
    "国家企业信用信息公示系统",
    "法院系统",
    "律所案件台账",
    "内部客户库",
    "内部数据库",
    "合同原件",
    "合同台账",
    "对账单",
    "发票",
    "付款记录",
    "送达记录",
    "证据目录",
    "附件清单",
    "客户确认材料",
    "其他",
]


def source_options_for_fields(fields: Iterable[ExtractedReviewField]) -> list[str]:
    options: list[str] = []
    for field in fields:
        for source in field.suggested_review_sources:
            if source not in options:
                options.append(source)
    for source in DEFAULT_REVIEW_SOURCES:
        if source not in options:
            options.append(source)
    return options


def default_manual_records(review_id: str, fields: list[ExtractedReviewField]) -> list[ManualReviewRecord]:
    return [
        ManualReviewRecord(
            record_id=stable_id("manual", review_id, field.field_id),
            review_id=review_id,
            field_id=field.field_id,
            field_type=field.field_type,
            extracted_value=field.value,
            source_location=field.source_location,
        )
        for field in fields
    ]


def manual_records_to_editor_dataframe(
    records: list[ManualReviewRecord],
    fields: list[ExtractedReviewField],
) -> pd.DataFrame:
    field_by_id = {field.field_id: field for field in fields}
    rows = []
    for record in records:
        field = field_by_id.get(record.field_id)
        rows.append(
            {
                "record_id": record.record_id,
                "field_id": record.field_id,
                "字段类型": record.field_type,
                "提取值": record.extracted_value,
                "角色 / 上下文": field.role_or_context if field else None,
                "出现位置": record.source_location,
                "建议复核来源": " / ".join(field.suggested_review_sources) if field else "",
                "建议动作": field.suggested_action if field else "建议人工复核该字段是否与外部基础材料一致。",
                "复核状态": record.review_status,
                "人工确认值": record.confirmed_value or "",
                "实际复核来源": record.review_source or "",
                "复核备注": record.reviewer_note or "",
            }
        )
    return pd.DataFrame(rows)


def editor_dataframe_to_manual_records(review_id: str, df: pd.DataFrame) -> list[ManualReviewRecord]:
    records: list[ManualReviewRecord] = []
    now = datetime.now()
    for row in df.to_dict("records"):
        status = row.get("复核状态") or "未复核"
        reviewed_at = now if status != "未复核" else None
        records.append(
            ManualReviewRecord(
                record_id=str(row["record_id"]),
                review_id=review_id,
                field_id=str(row["field_id"]),
                field_type=str(row.get("字段类型") or ""),
                extracted_value=str(row.get("提取值") or ""),
                confirmed_value=_clean_optional(row.get("人工确认值")),
                review_status=status,
                review_source=_clean_optional(row.get("实际复核来源")),
                reviewer_note=_clean_optional(row.get("复核备注")),
                source_location=str(row.get("出现位置") or "字段清单"),
                reviewed_at=reviewed_at,
            )
        )
    return records


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
