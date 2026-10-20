from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.models.schemas import (
    ExtractedReviewField,
    KnowledgeContext,
    ManualReviewRecord,
    ReviewFinding,
    StructuredExtractionResult,
)
from app.privacy.policy import PrivacyPolicy, default_privacy_policy
from app.privacy.redaction import build_privacy_summary
from app.reports.docx_annotation import annotated_docx_filename, build_annotated_docx
from app.reports.docx_report import build_docx_report
from app.reports.excel_report import build_excel_report
from app.reports.html_report import build_html_report


def build_review_package_zip(
    findings: list[ReviewFinding],
    external_fields: list[ExtractedReviewField] | None = None,
    manual_records: list[ManualReviewRecord] | None = None,
    review_id: str | None = None,
    mode_label: str = "完整复核模式",
    source_docx: str | bytes | None = None,
    source_filename: str | None = None,
    config_version: str | None = None,
    document_profile: str | None = None,
    config_updated_at: str | None = None,
    structured_extraction: StructuredExtractionResult | None = None,
    knowledge_context: KnowledgeContext | None = None,
    privacy_policy: PrivacyPolicy | None = None,
) -> bytes:
    policy = privacy_policy or default_privacy_policy()
    excel_bytes = build_excel_report(
        findings,
        external_fields,
        manual_records,
        config_version=config_version,
        document_profile=document_profile,
        config_updated_at=config_updated_at,
        structured_extraction=structured_extraction,
        knowledge_context=knowledge_context,
        privacy_policy=policy,
    )
    html = build_html_report(
        findings,
        external_fields,
        manual_records,
        mode_label=mode_label,
        config_version=config_version,
        document_profile=document_profile,
        config_updated_at=config_updated_at,
        structured_extraction=structured_extraction,
        knowledge_context=knowledge_context,
        privacy_policy=policy,
    )
    docx_bytes = build_docx_report(
        findings,
        external_fields,
        manual_records,
        review_id=review_id,
        mode_label=mode_label,
        config_version=config_version,
        document_profile=document_profile,
        config_updated_at=config_updated_at,
        structured_extraction=structured_extraction,
        knowledge_context=knowledge_context,
        privacy_policy=policy,
    )

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("复核工作底稿.xlsx", excel_bytes)
        package.writestr("复核报告.html", html.encode("utf-8"))
        package.writestr("文书复核摘要.docx", docx_bytes)
        if policy.include_privacy_summary_in_exports:
            package.writestr("privacy_summary.json", json.dumps(build_privacy_summary(policy), ensure_ascii=False, indent=2))
        if source_docx is not None and source_filename:
            annotated = build_annotated_docx(source_docx, findings, external_fields, manual_records)
            package.writestr(f"复核提示版文书/{annotated_docx_filename(source_filename)}", annotated)
    return output.getvalue()
