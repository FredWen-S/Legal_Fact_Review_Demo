from __future__ import annotations

import hashlib
import re
from typing import Iterable


SENSITIVE_FIELDS = {"身份证号", "手机号", "统一社会信用代码"}


def stable_id(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def mask_sensitive(value: str | None, field_name: str | None = None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if field_name in SENSITIVE_FIELDS or re.fullmatch(r"\d{17}[\dXx]", text):
        return text[:4] + "*" * max(4, len(text) - 8) + text[-4:]
    if re.fullmatch(r"1[3-9]\d{9}", text):
        return text[:3] + "****" + text[-4:]
    if re.fullmatch(r"[0-9A-Z]{18}", text):
        return text[:4] + "*" * 10 + text[-4:]
    return text


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip("：:，,。；;")


def unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
