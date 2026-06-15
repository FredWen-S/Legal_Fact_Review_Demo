from __future__ import annotations

from typing import cast

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.extractors.field_extractor import extract_fields
from app.models.schemas import BaseInfoItem, EvidenceItem, ReviewFinding, TextChunk
from app.validators.consistency_rules import (
    check_amount_inconsistency,
    check_date_logic,
    check_internal_conflicts,
    check_party_name_conflicts,
)
from app.validators.evidence_rules import check_evidence_references
from app.validators.format_rules import check_format_errors, check_placeholders
from app.validators.source_compare_rules import (
    check_missing_fields,
    check_possibly_outdated,
    check_source_mismatch,
)


def review_single_document(chunks: list[TextChunk], config: ReviewRulesConfig | None = None) -> list[ReviewFinding]:
    config = config or load_review_config()
    items = extract_fields(chunks, config=config)
    findings: list[ReviewFinding] = []
    findings.extend(check_placeholders(items))
    findings.extend(check_format_errors(items, chunks))
    findings.extend(check_internal_conflicts(items))
    findings.extend(check_party_name_conflicts(items))
    findings.extend(check_amount_inconsistency(items))
    findings.extend(check_date_logic(items))
    enabled_findings = [finding for finding in findings if config.risk_enabled(finding.risk_type)]
    configured_findings = [
        finding.model_copy(update={"severity": cast(str, config.severity_for(finding.risk_type, finding.severity))})
        for finding in enabled_findings
    ]
    return _dedupe(configured_findings)


def review_document(
    chunks: list[TextChunk],
    base_info: list[BaseInfoItem],
    evidence_index: list[EvidenceItem],
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> list[ReviewFinding]:
    config = config or load_review_config()
    items = extract_fields(chunks, config=config)
    findings: list[ReviewFinding] = []
    findings.extend(check_placeholders(items))
    findings.extend(check_format_errors(items, chunks))
    findings.extend(check_internal_conflicts(items))
    findings.extend(check_party_name_conflicts(items))
    findings.extend(check_amount_inconsistency(items))
    findings.extend(check_date_logic(items))
    findings.extend(check_source_mismatch(items, base_info))
    findings.extend(check_missing_fields(items, base_info, config=config, document_profile=document_profile))
    findings.extend(check_possibly_outdated(items, base_info))
    findings.extend(check_evidence_references(items, evidence_index))
    enabled_findings = [finding for finding in findings if config.risk_enabled(finding.risk_type)]
    configured_findings = [
        finding.model_copy(update={"severity": cast(str, config.severity_for(finding.risk_type, finding.severity))})
        for finding in enabled_findings
    ]
    return _dedupe(configured_findings)


def _dedupe(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[str] = set()
    result: list[ReviewFinding] = []
    for finding in findings:
        key = finding.risk_id
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return sorted(result, key=lambda item: {"high": 0, "medium": 1, "low": 2}[item.severity])
