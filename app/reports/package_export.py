from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.models.schemas import ExtractedReviewField, ManualReviewRecord, ReviewFinding
from app.reports.docx_report import build_docx_report
from app.reports.excel_report import build_excel_report
from app.reports.html_report import build_html_report


def build_review_package_zip(
    findings: list[ReviewFinding],
    external_fields: list[ExtractedReviewField] | None = None,
    manual_records: list[ManualReviewRecord] | None = None,
    review_id: str | None = None,
    mode_label: str = "完整复核模式",
) -> bytes:
    excel_bytes = build_excel_report(findings, external_fields, manual_records)
    html = build_html_report(findings, external_fields, manual_records, mode_label=mode_label)
    docx_bytes = build_docx_report(
        findings,
        external_fields,
        manual_records,
        review_id=review_id,
        mode_label=mode_label,
    )

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("复核工作底稿.xlsx", excel_bytes)
        package.writestr("复核报告.html", html.encode("utf-8"))
        package.writestr("文书复核摘要.docx", docx_bytes)
    return output.getvalue()
