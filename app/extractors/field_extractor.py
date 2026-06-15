from __future__ import annotations

import re

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.extractors.regex_extractor import extract_by_regex
from app.models.schemas import ExtractedItem, TextChunk


ROLE_PATTERN = re.compile(r"^(原告|被告|申请人|被申请人|甲方|乙方)[:：]\s*(.+)")
LABEL_PATTERNS: dict[str, re.Pattern[str]] = {
    "法定代表人": re.compile(r"法定代表人[:：]\s*([\u4e00-\u9fa5A-Za-z·]{2,30})"),
    "地址": re.compile(r"(?:住所地|地址)[:：]\s*(.+)"),
    "法院 / 仲裁机构名称": re.compile(r"([\u4e00-\u9fa5]{2,40}(?:人民法院|仲裁委员会))"),
    "案号原文": re.compile(r"案号[:：]\s*([^\s，。；;]+)"),
    "利息起算日": re.compile(r"利息(?:自|起算日[:：])\s*(\d{4}年\d{1,2}月\d{1,2}日)"),
}
CONFIG_FIELD_OUTPUT_NAMES = {
    "party_name": "当事人名称",
    "credit_code": "统一社会信用代码",
    "id_number": "身份证号",
    "legal_representative": "法定代表人",
    "address": "地址",
    "case_number": "案号原文",
    "contract_number": "合同编号",
    "amount": "金额",
    "date": "日期",
    "evidence_number": "证据编号",
    "attachment_number": "附件编号",
}


def extract_fields(chunks: list[TextChunk], config: ReviewRulesConfig | None = None) -> list[ExtractedItem]:
    config = config or load_review_config()
    items = extract_by_regex(chunks, config=config)
    configured_label_patterns = _configured_label_patterns(config)
    for chunk in chunks:
        role_match = ROLE_PATTERN.search(chunk.text)
        if role_match:
            role, value = role_match.groups()
            clean_value = re.split(r"[，,。；;]", value.strip())[0].strip()
            items.append(
                ExtractedItem(
                    field_name="当事人名称",
                    value=clean_value,
                    source_location=chunk.location,
                    confidence=0.85,
                    context=chunk.text[:300],
                )
            )
            items.append(
                ExtractedItem(
                    field_name="主体角色",
                    value=role,
                    source_location=chunk.location,
                    confidence=0.9,
                    context=chunk.text[:300],
                )
            )
        for field_name, pattern in LABEL_PATTERNS.items():
            for match in pattern.finditer(chunk.text):
                items.append(
                    ExtractedItem(
                        field_name=field_name,
                        value=match.group(1).strip(),
                        source_location=chunk.location,
                        confidence=0.82,
                        context=chunk.text[:300],
                    )
                )
        for field_name, pattern in configured_label_patterns:
            for match in pattern.finditer(chunk.text):
                items.append(
                    ExtractedItem(
                        field_name=field_name,
                        value=match.group(1).strip(),
                        source_location=chunk.location,
                        confidence=0.78,
                        context=chunk.text[:300],
                    )
                )
    return _dedupe_items(items)


def items_by_field(items: list[ExtractedItem]) -> dict[str, list[ExtractedItem]]:
    grouped: dict[str, list[ExtractedItem]] = {}
    for item in items:
        grouped.setdefault(item.field_name, []).append(item)
    return grouped


def _configured_label_patterns(config: ReviewRulesConfig) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for key, field_config in config.field_dictionary.items():
        field_name = CONFIG_FIELD_OUTPUT_NAMES.get(key)
        if not field_name:
            continue
        aliases = [alias.strip() for alias in field_config.aliases if alias.strip()]
        if not aliases:
            continue
        alias_group = "|".join(re.escape(alias) for alias in sorted(set(aliases), key=len, reverse=True))
        patterns.append((field_name, re.compile(rf"(?:{alias_group})[:：]\s*([^，,。；;\n]+)")))
    return patterns


def _dedupe_items(items: list[ExtractedItem]) -> list[ExtractedItem]:
    seen: set[tuple[str, str, str]] = set()
    result: list[ExtractedItem] = []
    for item in items:
        key = (item.field_name, item.value, item.source_location)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
