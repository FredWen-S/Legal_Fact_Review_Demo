from __future__ import annotations

from app.extractors.statute_extractor import parse_normalized_citation
from app.models.schemas import ReviewFinding, StructuredExtractionResult
from app.rag.statute_library import find_statute
from app.utils import stable_id


def check_statute_references(structured_extraction: StructuredExtractionResult | None) -> list[ReviewFinding]:
    """Cross-check extracted statute citations against the local statute reference list."""
    if structured_extraction is None:
        return []

    findings: list[ReviewFinding] = []
    seen: set[str] = set()
    for entity in structured_extraction.by_type("statute_reference"):
        parsed = parse_normalized_citation(entity.normalized_value)
        if parsed is None or entity.normalized_value in seen:
            continue
        seen.add(entity.normalized_value)
        law_name, article = parsed
        statute = find_statute(law_name)

        if statute is None:
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("statute-unverified", entity.normalized_value),
                    risk_type="STATUTE_UNVERIFIED",
                    severity="low",
                    field_name="法条引用",
                    document_value=entity.value,
                    reference_value=None,
                    source_location=entity.source_location,
                    reference_source="kb/statutes",
                    confidence=0.6,
                    reason="The cited law is not in the local statute reference list, so its status and article range could not be cross-checked.",
                    suggested_action="建议人工复核该法律文件名称、效力状态及条文内容是否准确。",
                )
            )
            continue

        if statute.is_repealed:
            replacement = f"，相关规定可参见《{statute.replaced_by}》" if statute.replaced_by else ""
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("statute-repealed", entity.normalized_value),
                    risk_type="STATUTE_REPEALED",
                    severity="high",
                    field_name="法条引用",
                    document_value=entity.value,
                    reference_value=f"《{statute.title}》已于{statute.repealed_date or '（日期未知）'}废止{replacement}",
                    source_location=entity.source_location,
                    reference_source=str(statute.path),
                    confidence=0.9,
                    reason="The cited law is marked as repealed in the statute reference list.",
                    suggested_action="建议人工复核该引用是否应改为现行有效法律的对应条文，或确认案件事实是否适用旧法。",
                )
            )
            continue

        if statute.article_count and article > statute.article_count:
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("statute-article-range", entity.normalized_value),
                    risk_type="STATUTE_ARTICLE_OUT_OF_RANGE",
                    severity="high",
                    field_name="法条引用",
                    document_value=entity.value,
                    reference_value=f"《{statute.title}》共{statute.article_count}条",
                    source_location=entity.source_location,
                    reference_source=str(statute.path),
                    confidence=0.88,
                    reason="The cited article number exceeds the number of articles in the referenced law.",
                    suggested_action="建议人工复核条文序号是否录入错误，或是否引用了其他法律文件。",
                )
            )
    return findings
