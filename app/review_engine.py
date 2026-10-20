from __future__ import annotations

from typing import cast

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.extractors.external_review_fields import build_external_review_fields
from app.extractors.field_extractor import extract_fields
from app.extractors.llm_extractor import extract_structured_entities, structured_entities_to_extracted_items
from app.llm.risk_explainer import explain_findings
from app.models.schemas import (
    BaseInfoItem,
    EvidenceItem,
    ExtractedItem,
    ReviewFinding,
    ReviewResult,
    TextChunk,
)
from app.rag.retrieval import build_knowledge_context
from app.validators.consistency_rules import (
    check_amount_inconsistency,
    check_date_logic,
    check_internal_conflicts,
    check_party_name_conflicts,
)
from app.validators.document_rules import (
    check_clause_numbering,
    check_profile_missing_fields,
    check_spelling_variations,
)
from app.validators.evidence_rules import check_evidence_references
from app.validators.format_rules import check_format_errors, check_placeholders
from app.validators.rag_rules import check_knowledge_alignment
from app.validators.source_compare_rules import (
    check_missing_fields,
    check_possibly_outdated,
    check_source_mismatch,
)
from app.validators.statute_rules import check_statute_references


def review_single_document(
    chunks: list[TextChunk],
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> list[ReviewFinding]:
    return review_single_document_result(chunks, config=config, document_profile=document_profile).findings


def review_document(
    chunks: list[TextChunk],
    base_info: list[BaseInfoItem],
    evidence_index: list[EvidenceItem],
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> list[ReviewFinding]:
    return review_document_result(
        chunks,
        base_info,
        evidence_index,
        config=config,
        document_profile=document_profile,
    ).findings


def review_single_document_result(
    chunks: list[TextChunk],
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> ReviewResult:
    return _run_review(
        chunks=chunks,
        base_info=[],
        evidence_index=[],
        config=config,
        document_profile=document_profile,
        compare_sources=False,
    )


def review_document_result(
    chunks: list[TextChunk],
    base_info: list[BaseInfoItem],
    evidence_index: list[EvidenceItem],
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> ReviewResult:
    return _run_review(
        chunks=chunks,
        base_info=base_info,
        evidence_index=evidence_index,
        config=config,
        document_profile=document_profile,
        compare_sources=True,
    )


def _run_review(
    chunks: list[TextChunk],
    base_info: list[BaseInfoItem],
    evidence_index: list[EvidenceItem],
    config: ReviewRulesConfig | None,
    document_profile: str | None,
    compare_sources: bool,
) -> ReviewResult:
    config = config or load_review_config()
    structured_extraction = extract_structured_entities(chunks)
    regex_items = extract_fields(chunks, config=config)
    structured_items = structured_entities_to_extracted_items(structured_extraction)
    items = _merge_items(regex_items + structured_items)
    knowledge_context = build_knowledge_context(chunks, structured_extraction)

    findings: list[ReviewFinding] = []
    if document_profile:
        findings.extend(check_profile_missing_fields(items, config=config, document_profile=document_profile))
    findings.extend(check_placeholders(items))
    findings.extend(check_format_errors(items, chunks))
    findings.extend(check_internal_conflicts(items))
    findings.extend(check_party_name_conflicts(items))
    findings.extend(check_amount_inconsistency(items))
    findings.extend(check_date_logic(items))
    findings.extend(check_spelling_variations(items, structured_extraction))
    findings.extend(check_clause_numbering(chunks))
    findings.extend(check_knowledge_alignment(chunks, structured_extraction, knowledge_context))
    findings.extend(check_statute_references(structured_extraction))

    if compare_sources:
        findings.extend(check_source_mismatch(items, base_info))
        findings.extend(check_missing_fields(items, base_info, config=config, document_profile=document_profile))
        findings.extend(check_possibly_outdated(items, base_info))
        findings.extend(check_evidence_references(items, evidence_index))

    enabled_findings = [finding for finding in findings if config.risk_enabled(finding.risk_type)]
    configured_findings = [
        finding.model_copy(
            update={"severity": cast(str, config.severity_for(finding.risk_type, finding.severity))}
        )
        for finding in enabled_findings
    ]
    external_fields = build_external_review_fields(
        chunks,
        config=config,
        structured_extraction=structured_extraction,
    )
    explained_findings, risk_explanation = explain_findings(_dedupe(configured_findings), chunks)
    return ReviewResult(
        findings=explained_findings,
        external_fields=external_fields,
        structured_extraction=structured_extraction,
        knowledge_context=knowledge_context,
        risk_explanation=risk_explanation,
    )


def _merge_items(items: list[ExtractedItem]) -> list[ExtractedItem]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[ExtractedItem] = []
    for item in items:
        key = (item.field_name, item.value, item.source_location)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _dedupe(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[str] = set()
    result: list[ReviewFinding] = []
    for finding in findings:
        key = finding.risk_id
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return sorted(result, key=lambda item: {"high": 0, "medium": 1, "low": 2}[item.severity])
