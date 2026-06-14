from __future__ import annotations

import re

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


def extract_fields(chunks: list[TextChunk]) -> list[ExtractedItem]:
    items = extract_by_regex(chunks)
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
    return items


def items_by_field(items: list[ExtractedItem]) -> dict[str, list[ExtractedItem]]:
    grouped: dict[str, list[ExtractedItem]] = {}
    for item in items:
        grouped.setdefault(item.field_name, []).append(item)
    return grouped
