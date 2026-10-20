from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.models.schemas import (
    ExtractedReviewField,
    KnowledgeContext,
    ManualReviewRecord,
    ReviewFinding,
    StructuredExtractionResult,
)
from app.privacy.policy import PrivacyPolicy, default_privacy_policy
from app.privacy.redaction import build_privacy_summary, redact_text
from app.utils import mask_sensitive


ISSUE_COLUMNS = [
    "Severity",
    "Issue Type",
    "Original Text",
    "Suggested Text",
    "Evidence Source",
    "Explanation",
    "Field Name",
    "Reference Value",
    "Reference Source",
    "Confidence",
]

EXTERNAL_FIELD_COLUMNS = {
    "field_type": "Field Type",
    "value": "Extracted Value",
    "role_or_context": "Role / Context",
    "source_location": "Source Location",
    "confidence": "Confidence",
    "suggested_review_sources": "Suggested Review Sources",
    "suggested_action": "Suggested Action",
}

MANUAL_RECORD_COLUMNS = {
    "field_type": "Field Type",
    "extracted_value": "Extracted Value",
    "confirmed_value": "Confirmed Value",
    "review_status": "Review Status",
    "review_source": "Review Source",
    "reviewer_note": "Reviewer Note",
    "source_location": "Source Location",
    "reviewed_at": "Reviewed At",
}


def findings_to_dataframe(
    findings: list[ReviewFinding],
    privacy_policy: PrivacyPolicy | None = None,
) -> pd.DataFrame:
    policy = privacy_policy or default_privacy_policy()
    rows = []
    for finding in findings:
        issue = finding.to_issue_record()
        rows.append(
            {
                "Severity": issue["severity"],
                "Issue Type": issue["issue_type"],
                "Original Text": mask_sensitive(issue["original_text"], finding.field_name),
                "Suggested Text": issue["suggested_text"],
                "Evidence Source": issue["evidence_source"],
                "Explanation": issue["explanation"],
                "Field Name": issue["field_name"],
                "Reference Value": mask_sensitive(issue["reference_value"], finding.field_name),
                "Reference Source": issue["reference_source"],
                "Confidence": issue["confidence"],
            }
        )
    return _redact_dataframe(pd.DataFrame(rows, columns=ISSUE_COLUMNS), policy)


def external_fields_to_dataframe(
    fields: list[ExtractedReviewField],
    privacy_policy: PrivacyPolicy | None = None,
) -> pd.DataFrame:
    policy = privacy_policy or default_privacy_policy()
    rows = []
    for field in fields:
        row = field.model_dump()
        row["value"] = mask_sensitive(row.get("value"), row.get("field_type"))
        row["suggested_review_sources"] = " / ".join(row.get("suggested_review_sources") or [])
        rows.append({label: row.get(key) for key, label in EXTERNAL_FIELD_COLUMNS.items()})
    return _redact_dataframe(pd.DataFrame(rows, columns=list(EXTERNAL_FIELD_COLUMNS.values())), policy)


def manual_records_to_dataframe(
    records: list[ManualReviewRecord],
    privacy_policy: PrivacyPolicy | None = None,
) -> pd.DataFrame:
    policy = privacy_policy or default_privacy_policy()
    rows = []
    for record in records:
        row = record.model_dump()
        row["extracted_value"] = mask_sensitive(row.get("extracted_value"), row.get("field_type"))
        row["confirmed_value"] = mask_sensitive(row.get("confirmed_value"), row.get("field_type"))
        row["reviewed_at"] = record.reviewed_at.isoformat(timespec="seconds") if record.reviewed_at else None
        rows.append({label: row.get(key) for key, label in MANUAL_RECORD_COLUMNS.items()})
    return _redact_dataframe(pd.DataFrame(rows, columns=list(MANUAL_RECORD_COLUMNS.values())), policy)


def structured_extraction_to_dataframe(
    structured_extraction: StructuredExtractionResult | None,
    privacy_policy: PrivacyPolicy | None = None,
) -> pd.DataFrame:
    policy = privacy_policy or default_privacy_policy()
    if structured_extraction is None:
        return pd.DataFrame(columns=["Entity Type", "Value", "Normalized Value", "Role", "Source Location", "Confidence", "Fallback Reason"])

    rows = [
        {
            "Entity Type": entity.entity_type,
            "Value": entity.value,
            "Normalized Value": entity.normalized_value,
            "Role": entity.role,
            "Source Location": entity.source_location,
            "Confidence": entity.confidence,
            "Fallback Reason": structured_extraction.fallback_reason,
        }
        for entity in structured_extraction.entities
    ]
    return _redact_dataframe(
        pd.DataFrame(rows, columns=["Entity Type", "Value", "Normalized Value", "Role", "Source Location", "Confidence", "Fallback Reason"]),
        policy,
    )


def knowledge_context_to_dataframe(
    knowledge_context: KnowledgeContext | None,
    privacy_policy: PrivacyPolicy | None = None,
) -> pd.DataFrame:
    policy = privacy_policy or default_privacy_policy()
    if knowledge_context is None:
        return pd.DataFrame(columns=["KB Type", "Status", "Title", "Score", "Min Score", "Path", "Snippet", "Match Reason"])

    rows = []
    if knowledge_context.client_profile is not None:
        rows.append(
            {
                "KB Type": knowledge_context.client_profile.kb_type,
                "Status": knowledge_context.client_profile.match_status,
                "Title": knowledge_context.client_profile.title,
                "Score": knowledge_context.client_profile.score,
                "Min Score": knowledge_context.client_profile.min_score,
                "Path": knowledge_context.client_profile.path,
                "Snippet": knowledge_context.client_profile.snippet,
                "Match Reason": knowledge_context.client_profile.match_reason,
            }
        )
    for match in knowledge_context.templates + knowledge_context.clauses:
        rows.append(
            {
                "KB Type": match.kb_type,
                "Status": match.match_status,
                "Title": match.title,
                "Score": match.score,
                "Min Score": match.min_score,
                "Path": match.path,
                "Snippet": match.snippet,
                "Match Reason": match.match_reason,
            }
        )
    matched_keys = {(row["KB Type"], row["Status"]) for row in rows}
    for status in knowledge_context.retrieval_statuses:
        if status.status == "matched" and (status.kb_type, status.status) in matched_keys:
            continue
        rows.append(
            {
                "KB Type": status.kb_type,
                "Status": status.status,
                "Title": status.best_doc_id or "",
                "Score": status.best_score,
                "Min Score": status.min_score,
                "Path": "",
                "Snippet": "",
                "Match Reason": status.match_reason,
            }
        )
    return _redact_dataframe(
        pd.DataFrame(rows, columns=["KB Type", "Status", "Title", "Score", "Min Score", "Path", "Snippet", "Match Reason"]),
        policy,
    )


def build_excel_report(
    findings: list[ReviewFinding],
    external_fields: list[ExtractedReviewField] | None = None,
    manual_records: list[ManualReviewRecord] | None = None,
    config_version: str | None = None,
    document_profile: str | None = None,
    config_updated_at: str | None = None,
    structured_extraction: StructuredExtractionResult | None = None,
    knowledge_context: KnowledgeContext | None = None,
    privacy_policy: PrivacyPolicy | None = None,
) -> bytes:
    policy = privacy_policy or default_privacy_policy()
    output = BytesIO()
    issues_df = findings_to_dataframe(findings, policy)
    external_df = external_fields_to_dataframe(external_fields or [], policy)
    manual_df = manual_records_to_dataframe(manual_records or [], policy)
    extraction_df = structured_extraction_to_dataframe(structured_extraction, policy)
    knowledge_df = knowledge_context_to_dataframe(knowledge_context, policy)
    privacy_df = privacy_summary_to_dataframe(policy)
    severity_counts = {
        "HIGH": sum(1 for finding in findings if finding.severity == "high"),
        "MEDIUM": sum(1 for finding in findings if finding.severity == "medium"),
        "LOW": sum(1 for finding in findings if finding.severity == "low"),
    }

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        meta_df = pd.DataFrame(
            [
                ("Config Version", config_version or ""),
                ("Document Profile", document_profile or ""),
                ("Config Updated At", config_updated_at or ""),
                ("Issue Count", len(findings)),
                ("HIGH", severity_counts["HIGH"]),
                ("MEDIUM", severity_counts["MEDIUM"]),
                ("LOW", severity_counts["LOW"]),
                ("Extraction Mode", structured_extraction.mode if structured_extraction else ""),
                ("Extraction Model", structured_extraction.model_name if structured_extraction else ""),
                ("Extraction Fallback Reason", structured_extraction.fallback_reason if structured_extraction else ""),
            ],
            columns=["Item", "Value"],
        )
        meta_df.to_excel(writer, index=False, sheet_name="Metadata")
        issues_df.to_excel(writer, index=False, sheet_name="Issues")
        extraction_df.to_excel(writer, index=False, sheet_name="Structured Extraction")
        knowledge_df.to_excel(writer, index=False, sheet_name="Retrieved Knowledge")
        external_df.to_excel(writer, index=False, sheet_name="Review Workbench")
        manual_df.to_excel(writer, index=False, sheet_name="Manual Review")
        if policy.include_privacy_summary_in_exports:
            privacy_df.to_excel(writer, index=False, sheet_name="Privacy Summary")
        for worksheet in writer.sheets.values():
            for column_cells in worksheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 12), 48)
    return output.getvalue()


def privacy_summary_to_dataframe(privacy_policy: PrivacyPolicy | None = None) -> pd.DataFrame:
    policy = privacy_policy or default_privacy_policy()
    return pd.DataFrame(
        [{"Item": key, "Value": value} for key, value in build_privacy_summary(policy).items()],
        columns=["Item", "Value"],
    )


def _redact_dataframe(df: pd.DataFrame, policy: PrivacyPolicy) -> pd.DataFrame:
    if not policy.redact_report_sensitive_fields or df.empty:
        return df
    redacted = df.copy()
    for column in redacted.columns:
        redacted[column] = redacted[column].map(lambda value: redact_text(str(value), policy) if isinstance(value, str) else value)
    return redacted
