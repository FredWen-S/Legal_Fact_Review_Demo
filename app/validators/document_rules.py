from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.models.schemas import ExtractedItem, ReviewFinding, StructuredExtractionResult, TextChunk
from app.utils import normalize_text, stable_id


CHINESE_NUMERALS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
CLAUSE_PATTERNS = [
    re.compile(r"^第([一二三四五六七八九十零\d]+)条"),
    re.compile(r"^(\d+)[.、]\s*"),
]


def check_profile_missing_fields(
    items: list[ExtractedItem],
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> list[ReviewFinding]:
    config = config or load_review_config()
    required_fields = config.critical_fields_for_profile(document_profile)
    item_fields = {item.field_name for item in items}
    findings: list[ReviewFinding] = []
    for field_name in required_fields:
        if field_name not in item_fields:
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("profile-missing", document_profile or "general", field_name),
                    risk_type="MISSING_FIELD",
                    severity="medium",
                    field_name=field_name,
                    document_value=None,
                    reference_value=field_name,
                    source_location="全文检索",
                    reference_source=f"文书模板:{document_profile or 'general'}",
                    confidence=0.7,
                    reason=f"Current document profile expects '{field_name}', but no corresponding value was extracted.",
                    suggested_action="建议人工复核该必填字段是否缺失，或确认文书是否使用了不同表述。",
                )
            )
    return findings


def check_spelling_variations(
    items: list[ExtractedItem],
    structured_extraction: StructuredExtractionResult | None = None,
) -> list[ReviewFinding]:
    candidates: list[tuple[str, str, str]] = []

    for item in items:
        if item.field_name == "当事人名称" and any(keyword in item.value for keyword in ("公司", "集团", "事务所", "研究院")):
            candidates.append((item.value, item.source_location, item.context or ""))

    if structured_extraction is not None:
        for entity in structured_extraction.by_type("company_name"):
            candidates.append((entity.value, entity.source_location, entity.context or ""))

    deduped: list[tuple[str, str, str]] = []
    seen_values: set[tuple[str, str]] = set()
    for value, location, context in candidates:
        key = (value, location)
        if key in seen_values:
            continue
        seen_values.add(key)
        deduped.append((value, location, context))

    findings: list[ReviewFinding] = []
    for index, (left_value, left_location, _) in enumerate(deduped):
        for right_value, right_location, _ in deduped[index + 1 :]:
            left_norm = normalize_text(left_value)
            right_norm = normalize_text(right_value)
            if not left_norm or not right_norm or left_norm == right_norm:
                continue
            similarity = SequenceMatcher(None, left_norm, right_norm).ratio()
            if similarity < 0.84:
                continue
            preferred = max((left_value, right_value), key=len)
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("spelling", left_value, right_value),
                    risk_type="SPELLING_VARIATION",
                    severity="medium",
                    field_name="当事人名称",
                    document_value=f"{left_value} / {right_value}",
                    reference_value=preferred,
                    source_location=f"{left_location}; {right_location}",
                    reference_source="Document internal consistency",
                    confidence=0.82,
                    reason="Two company names are highly similar but not identical, which suggests a spelling inconsistency.",
                    suggested_action="建议人工复核公司名称的正确写法，并统一全文表述。",
                )
            )
    return findings


def check_clause_numbering(chunks: list[TextChunk]) -> list[ReviewFinding]:
    clause_rows: list[tuple[int, TextChunk, str]] = []
    for chunk in chunks:
        text = chunk.text.strip()
        for pattern in CLAUSE_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue
            number = _parse_clause_number(match.group(1))
            if number is None:
                continue
            clause_rows.append((number, chunk, text))
            break

    if len(clause_rows) < 2:
        return []

    findings: list[ReviewFinding] = []
    first_number = clause_rows[0][0]
    if first_number != 1:
        findings.append(
            ReviewFinding(
                risk_id=stable_id("clause-start", first_number, clause_rows[0][1].location),
                risk_type="CLAUSE_NUMBERING_ERROR",
                severity="medium",
                field_name="条款编号",
                document_value=clause_rows[0][2],
                reference_value="Expected clause numbering to start at 1",
                source_location=clause_rows[0][1].location,
                reference_source="Clause numbering rule",
                confidence=0.78,
                reason="Clause numbering appears to start from a non-standard index.",
                suggested_action="建议人工复核条款编号起始值，确认是否应从第1条开始。",
            )
        )

    previous_number = clause_rows[0][0]
    for number, chunk, text in clause_rows[1:]:
        expected = previous_number + 1
        if number != expected:
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("clause-sequence", previous_number, number, chunk.location),
                    risk_type="CLAUSE_NUMBERING_ERROR",
                    severity="medium",
                    field_name="条款编号",
                    document_value=text,
                    reference_value=f"Expected clause number {expected}",
                    source_location=chunk.location,
                    reference_source="Clause numbering rule",
                    confidence=0.8,
                    reason="Clause numbering is duplicated or skips a number.",
                    suggested_action="建议人工复核条款编号，修正重复编号或缺失编号。",
                )
            )
        previous_number = number
    return findings


def _parse_clause_number(raw_value: str) -> int | None:
    raw_value = raw_value.strip()
    if raw_value.isdigit():
        return int(raw_value)
    if raw_value == "十":
        return 10
    if raw_value.startswith("十"):
        return 10 + CHINESE_NUMERALS.get(raw_value[1:], 0)
    if raw_value.endswith("十"):
        return CHINESE_NUMERALS.get(raw_value[0], 0) * 10
    if "十" in raw_value:
        left, right = raw_value.split("十", 1)
        return CHINESE_NUMERALS.get(left, 0) * 10 + CHINESE_NUMERALS.get(right, 0)
    if raw_value in CHINESE_NUMERALS:
        return CHINESE_NUMERALS[raw_value]
    return None
