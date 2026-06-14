from app.models.schemas import ExtractedReviewField, ManualReviewRecord, ReviewFinding
from app.reports.excel_report import build_excel_report
from app.reports.html_report import build_html_report


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
