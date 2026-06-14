from __future__ import annotations

from datetime import datetime

from app.config.review_config import load_review_config
from app.models.schemas import BaseInfoItem, ExtractedItem, ReviewFinding
from app.utils import normalize_text, stable_id


DEFAULT_CRITICAL_FIELDS = ["当事人名称", "法定代表人", "地址", "统一社会信用代码", "案号"]


def check_source_mismatch(items: list[ExtractedItem], base_info: list[BaseInfoItem]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    by_field = {item.field_name: item for item in base_info}
    for field_name, base in by_field.items():
        candidates = _candidate_items(field_name, items)
        if any(normalize_text(item.value) == normalize_text(base.standard_value) for item in candidates):
            continue
        for item in candidates:
            if normalize_text(item.value) and normalize_text(base.standard_value) and normalize_text(item.value) != normalize_text(base.standard_value):
                findings.append(
                    ReviewFinding(
                        risk_id=stable_id("source", field_name, item.value, base.standard_value, item.source_location),
                        risk_type="SOURCE_MISMATCH",
                        severity="high" if field_name in {"当事人名称", "法定代表人", "统一社会信用代码"} else "medium",
                        field_name=field_name,
                        document_value=item.value,
                        reference_value=base.standard_value,
                        source_location=item.source_location,
                        reference_source="基础信息表",
                        confidence=0.86,
                        reason=f"文书中的“{field_name}”与基础信息表标准值不一致，需要复核是否使用了最新信息。",
                        suggested_action="建议人工复核最新版基础信息表，并确认文书该字段是否需要更新。",
                    )
                )
    return _dedupe(findings)


def check_missing_fields(items: list[ExtractedItem], base_info: list[BaseInfoItem]) -> list[ReviewFinding]:
    base_fields = {item.field_name for item in base_info}
    config = load_review_config()
    critical_fields = config.critical_fields or DEFAULT_CRITICAL_FIELDS
    findings: list[ReviewFinding] = []
    for field_name in critical_fields:
        if field_name in base_fields and not _candidate_items(field_name, items):
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("missing", field_name),
                    risk_type="MISSING_FIELD",
                    severity="medium",
                    field_name=field_name,
                    document_value=None,
                    reference_value=next((item.standard_value for item in base_info if item.field_name == field_name), None),
                    source_location="全文检索",
                    reference_source="基础信息表",
                    confidence=0.68,
                    reason=f"基础信息表包含“{field_name}”，但文书中未识别到对应字段。",
                    suggested_action="建议人工复核文书是否遗漏该关键字段，或确认字段表述是否需要调整。",
                )
            )
    return findings


def check_possibly_outdated(items: list[ExtractedItem], base_info: list[BaseInfoItem]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    latest_base_date = None
    for base in base_info:
        parsed = _parse_any_date(base.updated_at)
        if parsed and (latest_base_date is None or parsed > latest_base_date):
            latest_base_date = parsed
    if latest_base_date is None:
        return []
    for item in items:
        if item.field_name != "日期":
            continue
        parsed = _parse_any_date(item.value)
        if parsed and latest_base_date > parsed and item.context and ("基础信息" in item.context or "版本" in item.context):
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("outdated", item.value, item.source_location),
                    risk_type="POSSIBLY_OUTDATED",
                    severity="low",
                    field_name="基础信息版本日期",
                    document_value=item.value,
                    reference_value=latest_base_date.strftime("%Y-%m-%d"),
                    source_location=item.source_location,
                    reference_source="基础信息表更新时间",
                    confidence=0.62,
                    reason="基础信息表更新时间晚于文书中出现的基础信息或版本日期，可能使用了旧版本信息。",
                    suggested_action="建议人工复核最新版基础信息表，确认文书是否需要同步更新。",
                )
            )
    return findings


def _candidate_items(field_name: str, items: list[ExtractedItem]) -> list[ExtractedItem]:
    if field_name == "案号":
        return [item for item in items if item.field_name in {"案号", "案号原文"}]
    return [item for item in items if item.field_name == field_name]


def _parse_any_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _dedupe(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[str] = set()
    result: list[ReviewFinding] = []
    for finding in findings:
        key = f"{finding.risk_type}|{finding.field_name}|{finding.document_value}|{finding.reference_value}|{finding.source_location}"
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return result
