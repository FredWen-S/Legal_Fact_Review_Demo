from __future__ import annotations

import re

from app.config.review_config import load_review_config
from app.models.schemas import ExtractedItem, TextChunk


PATTERNS: dict[str, re.Pattern[str]] = {
    "统一社会信用代码": re.compile(r"(?<![0-9A-Z])[0-9A-Z]{18}(?![0-9A-Z])"),
    "身份证号": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "案号": re.compile(r"[（(]\d{4}[）)][\u4e00-\u9fa5A-Za-z0-9]+(?:初|终|申|执|民|商|行|刑)[\u4e00-\u9fa5A-Za-z0-9]*号"),
    "日期": re.compile(r"\d{4}年\d{1,2}月\d{1,2}日"),
    "金额": re.compile(r"(?:人民币)?[0-9][0-9,]*(?:\.\d+)?\s*元"),
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "邮箱": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "合同编号": re.compile(r"(?:合同编号|编号)[:：]?\s*([A-Za-z0-9\-]{4,})"),
    "证据编号": re.compile(r"证据\s*([一二三四五六七八九十\d]+)"),
    "附件编号": re.compile(r"附件\s*([一二三四五六七八九十\d]+)"),
}

def _placeholder_pattern() -> re.Pattern[str]:
    config = load_review_config()
    patterns = config.placeholder_patterns or ["待补充", "X{2,}", "x{2,}", "某某", "202X", "20XX", r"【\s*】", "____+"]
    return re.compile("|".join(patterns))


def extract_by_regex(chunks: list[TextChunk]) -> list[ExtractedItem]:
    items: list[ExtractedItem] = []
    for chunk in chunks:
        for field_name, pattern in PATTERNS.items():
            for match in pattern.finditer(chunk.text):
                value = match.group(1) if field_name in {"合同编号", "证据编号", "附件编号"} else match.group(0)
                items.append(
                    ExtractedItem(
                        field_name=field_name,
                        value=value.strip(),
                        source_location=chunk.location,
                        confidence=0.9,
                        context=chunk.text[:300],
                    )
                )
        for match in _placeholder_pattern().finditer(chunk.text):
            items.append(
                ExtractedItem(
                    field_name="文书中的占位符",
                    value=match.group(0),
                    source_location=chunk.location,
                    confidence=0.95,
                    context=chunk.text[:300],
                )
            )
    return items
