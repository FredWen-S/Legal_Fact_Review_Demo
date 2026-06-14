from __future__ import annotations

from datetime import datetime
import re

from app.extractors.field_extractor import items_by_field
from app.models.schemas import ExtractedItem, ReviewFinding
from app.utils import normalize_text, stable_id, unique_keep_order


def check_internal_conflicts(items: list[ExtractedItem]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    grouped = items_by_field(items)
    for field_name in ["法定代表人", "法院 / 仲裁机构名称", "合同编号"]:
        values = unique_keep_order(normalize_text(item.value) for item in grouped.get(field_name, []))
        if len(values) > 1:
            source = grouped[field_name][0].source_location
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("internal", field_name, *values),
                    risk_type="INTERNAL_CONFLICT",
                    severity="high",
                    field_name=field_name,
                    document_value=" / ".join(values),
                    reference_value=None,
                    source_location=source,
                    confidence=0.86,
                    reason=f"同一字段“{field_name}”在文书中出现多个不同值。",
                    suggested_action="建议人工复核该字段各处表述，确认是否存在旧版本信息或复制粘贴残留。",
                )
            )
    return findings


def check_party_name_conflicts(items: list[ExtractedItem]) -> list[ReviewFinding]:
    parties = [item for item in items if item.field_name == "当事人名称"]
    company_like = [item for item in parties if "公司" in item.value]
    values = unique_keep_order(normalize_text(item.value) for item in company_like)
    if len(values) <= 1:
        return []
    return [
        ReviewFinding(
            risk_id=stable_id("party-conflict", *values),
            risk_type="INTERNAL_CONFLICT",
            severity="high",
            field_name="当事人名称",
            document_value=" / ".join(values),
            reference_value=None,
            source_location=company_like[0].source_location,
            confidence=0.82,
            reason="文书中当事人公司名称出现多个不同版本，可能存在名称未统一或旧版本信息残留。",
            suggested_action="建议人工复核营业执照、基础信息表或委托材料，并统一全文当事人名称。",
        )
    ]


def check_amount_inconsistency(items: list[ExtractedItem]) -> list[ReviewFinding]:
    amount_items = [item for item in items if item.field_name == "金额"]
    normalized = unique_keep_order(_amount_number(item.value) for item in amount_items)
    normalized = [value for value in normalized if value]
    if len(normalized) <= 1:
        return []
    return [
        ReviewFinding(
            risk_id=stable_id("amount", *normalized),
            risk_type="AMOUNT_INCONSISTENCY",
            severity="high",
            field_name="金额",
            document_value=" / ".join(normalized),
            reference_value=None,
            source_location=amount_items[0].source_location,
            confidence=0.84,
            reason="文书中出现多个不同金额，可能涉及诉讼请求、事实陈述或合同金额不一致。",
            suggested_action="建议人工复核文书正文与诉讼请求金额是否一致，并确认各金额的计算口径。",
        )
    ]


def check_date_logic(items: list[ExtractedItem]) -> list[ReviewFinding]:
    dated_context = []
    for item in items:
        if item.field_name != "日期" or not item.context:
            continue
        parsed = _parse_date(item.value)
        if parsed:
            dated_context.append((item, parsed, item.context))
    findings: list[ReviewFinding] = []
    sign_dates = [(item, date) for item, date, ctx in dated_context if "签署" in ctx or "签订" in ctx]
    deadline_dates = [(item, date) for item, date, ctx in dated_context if "履行截止" in ctx or "付款期限" in ctx]
    sue_dates = [(item, date) for item, date, ctx in dated_context if "起诉" in ctx]
    for deadline_item, deadline in deadline_dates:
        for sign_item, sign in sign_dates:
            if deadline < sign:
                findings.append(
                    ReviewFinding(
                        risk_id=stable_id("date-deadline", deadline_item.value, sign_item.value),
                        risk_type="DATE_LOGIC_WARNING",
                        severity="medium",
                        field_name="日期",
                        document_value=f"履行截止日 {deadline_item.value}；签署日 {sign_item.value}",
                        reference_value=None,
                        source_location=deadline_item.source_location,
                        confidence=0.78,
                        reason="履行截止日期早于合同签署日期，日期顺序疑似异常。",
                        suggested_action="建议人工复核合同签署日、履行期限和事实表述是否准确。",
                    )
                )
    for sue_item, sue in sue_dates:
        for sign_item, sign in sign_dates:
            if sue < sign:
                findings.append(
                    ReviewFinding(
                        risk_id=stable_id("date-sue", sue_item.value, sign_item.value),
                        risk_type="DATE_LOGIC_WARNING",
                        severity="medium",
                        field_name="日期",
                        document_value=f"起诉日 {sue_item.value}；签署日 {sign_item.value}",
                        reference_value=None,
                        source_location=sue_item.source_location,
                        confidence=0.72,
                        reason="起诉日期早于合同签署日期，日期顺序疑似异常。",
                        suggested_action="建议人工复核起诉日期、合同日期和案件时间线。",
                    )
                )
    return findings


def _amount_number(value: str) -> str:
    return re.sub(r"[^\d.]", "", value)


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y年%m月%d日")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y年%-m月%-d日")
        except ValueError:
            match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
            if not match:
                return None
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)
