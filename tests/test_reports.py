from app.models.schemas import ExtractedReviewField, ManualReviewRecord, ReviewFinding
from app.reports.docx_report import build_docx_report
from app.reports.excel_report import build_excel_report
from app.reports.html_report import build_html_report
from docx import Document
from io import BytesIO
from openpyxl import load_workbook


def _finding() -> ReviewFinding:
    return ReviewFinding(
        risk_id="r1",
        risk_type="PLACEHOLDER_REMAINING",
        severity="high",
        field_name="文书中的占位符",
        document_value="待补充",
        reference_value=None,
        source_location="段落1",
        confidence=0.95,
        reason="存在占位符。",
        suggested_action="建议人工复核该处内容。",
    )


def test_excel_report_generation():
    data = build_excel_report([_finding()], [_external_field()], [_manual_record()])
    assert data[:2] == b"PK"


def test_html_report_generation():
    html = build_html_report([_finding()], [_external_field()], [_manual_record()])
    assert "律师文书基础信息复核报告" in html
    assert "不构成法律意见" in html
    assert "待外部复核字段清单" in html
    assert "人工复核记录" in html


def test_reports_include_config_version_and_document_profile():
    excel = build_excel_report([_finding()], config_version="case09-custom-v1", document_profile="lawyer_letter")
    workbook = load_workbook(BytesIO(excel), data_only=True)
    meta = workbook["复核元数据"]
    values = {(row[0].value, row[1].value) for row in meta.iter_rows(min_row=2, max_col=2)}
    assert ("规则配置版本", "case09-custom-v1") in values
    assert ("文书类型模板", "lawyer_letter") in values

    html = build_html_report([_finding()], config_version="case09-custom-v1", document_profile="lawyer_letter")
    assert "case09-custom-v1" in html
    assert "lawyer_letter" in html

    docx = build_docx_report([_finding()], config_version="case09-custom-v1", document_profile="lawyer_letter")
    document = Document(BytesIO(docx))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    table_text = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
    combined = f"{text}\n{table_text}"
    assert "case09-custom-v1" in combined
    assert "lawyer_letter" in combined


def _external_field() -> ExtractedReviewField:
    return ExtractedReviewField(
        field_id="f1",
        field_type="案号",
        value="（2024）沪0115民初12345号",
        role_or_context="案件信息",
        source_location="段落1",
        confidence=0.9,
        suggested_review_sources=["法院系统", "案件台账"],
        suggested_action="建议人工复核案号格式和案件信息是否正确。",
    )


def _manual_record() -> ManualReviewRecord:
    return ManualReviewRecord(
        record_id="r1",
        review_id="review-1",
        field_id="f1",
        field_type="案号",
        extracted_value="（2024）沪0115民初12345号",
        review_status="未复核",
        source_location="段落1",
    )
