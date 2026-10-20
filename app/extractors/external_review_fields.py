from __future__ import annotations

import re

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.extractors.field_extractor import extract_fields
from app.extractors.llm_extractor import structured_entities_to_extracted_items
from app.models.schemas import (
    ExtractedItem,
    ExtractedReviewField,
    StructuredExtractionResult,
    TextChunk,
)
from app.utils import mask_sensitive, stable_id


FIELD_TYPE_TO_RULE_KEY = {
    "当事人名称": "company_name",
    "统一社会信用代码": "credit_code",
    "身份证号": "id_number",
    "法定代表人": "legal_representative",
    "地址": "address",
    "案号": "case_number",
    "案号原文": "case_number",
    "法院 / 仲裁机构名称": "institution",
    "合同编号": "contract_number",
    "金额": "amount",
    "日期": "date",
    "利息起算日": "date",
    "证据编号": "evidence_number",
    "附件编号": "attachment_number",
    "文书中的占位符": "placeholder",
}

DISPLAY_FIELD_TYPES = {
    "案号原文": "案号",
    "法院 / 仲裁机构名称": "法院 / 仲裁机构",
    "文书中的占位符": "占位符",
}


def build_external_review_fields(
    chunks: list[TextChunk],
    config: ReviewRulesConfig | None = None,
    structured_extraction: StructuredExtractionResult | None = None,
) -> list[ExtractedReviewField]:
    config = config or load_review_config()
    extracted_items = _review_items(chunks, config, structured_extraction)
    fields: list[ExtractedReviewField] = []
    for item in extracted_items:
        if item.field_name == "主体角色":
            continue
        rule_key = FIELD_TYPE_TO_RULE_KEY.get(item.field_name)
        if not rule_key:
            continue
        rule = config.external_review_rule(rule_key)
        sources = [str(source) for source in rule.get("sources", []) if str(source).strip()]
        suggested_action = str(
            rule.get("suggested_action")
            or "建议人工复核该字段，并与支持材料核对。"
        )
        field_type = DISPLAY_FIELD_TYPES.get(item.field_name, item.field_name)
        fields.append(
            ExtractedReviewField(
                field_id=stable_id("external-field", item.field_name, item.value, item.source_location),
                field_type=field_type,
                value=mask_sensitive(item.value, item.field_name) or "",
                role_or_context=_role_or_context(item),
                source_location=item.source_location,
                confidence=item.confidence,
                suggested_review_sources=sources,
                suggested_action=suggested_action,
            )
        )
    return _dedupe(fields)


def _review_items(
    chunks: list[TextChunk],
    config: ReviewRulesConfig,
    structured_extraction: StructuredExtractionResult | None,
) -> list[ExtractedItem]:
    regex_items = extract_fields(chunks, config=config)
    if structured_extraction is None:
        return regex_items
    combined = regex_items + structured_entities_to_extracted_items(structured_extraction)
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ExtractedItem] = []
    for item in combined:
        key = (item.field_name, item.value, item.source_location)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _role_or_context(item: ExtractedItem) -> str | None:
    context = item.context or ""
    role_match = re.search(r"(原告|被告|申请人|被申请人|甲方|乙方)[:：]", context)
    if role_match:
        role = role_match.group(1)
        if item.field_name == "地址":
            return f"{role}地址"
        return role
    if "诉讼请求" in context and item.field_name == "金额":
        return "诉讼请求"
    if "事实与理由" in context:
        return "事实与理由"
    if "利息" in context and item.field_name in {"日期", "利息起算日"}:
        return "利息起算日"
    if item.field_name in {"案号", "案号原文", "法院 / 仲裁机构名称"}:
        return "案件信息"
    return (context[:60] + "...") if len(context) > 60 else context or None


def _dedupe(fields: list[ExtractedReviewField]) -> list[ExtractedReviewField]:
    seen: set[str] = set()
    result: list[ExtractedReviewField] = []
    for field in fields:
        key = f"{field.field_type}|{field.value}|{field.source_location}"
        if key not in seen:
            seen.add(key)
            result.append(field)
    return result
