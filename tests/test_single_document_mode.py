from app.extractors.external_review_fields import build_external_review_fields
from app.models.schemas import TextChunk
from app.reports.excel_report import build_excel_report, external_fields_to_dataframe
from app.reports.html_report import build_html_report
from app.review_engine import review_single_document


def _single_document_chunks():
    return [
        TextChunk(text="案号：（2024）沪0115民初12345号", location="段落1"),
        TextChunk(text="原告：上海星河科技有限公司，统一社会信用代码：91310000MA1K000001，身份证号：110101199001011234。", location="段落2"),
        TextChunk(text="法定代表人：张三。住所地：上海市浦东新区示例路99号。", location="段落3"),
        TextChunk(text="诉讼请求：请求支付人民币1280000元，利息自2024年6月1日起算。", location="段落4"),
        TextChunk(text="证据7：付款催告函。其他事项：待补充。", location="段落5"),
    ]


def test_single_document_mode_runs_without_external_sources():
    findings = review_single_document(_single_document_chunks())
    assert findings


def test_single_document_mode_does_not_generate_external_compare_risks():
    findings = review_single_document(_single_document_chunks())
    risk_types = {finding.risk_type for finding in findings}
    assert "SOURCE_MISMATCH" not in risk_types
    assert "EVIDENCE_REFERENCE_MISSING" not in risk_types


def test_single_document_mode_builds_external_review_fields():
    fields = build_external_review_fields(_single_document_chunks())
    assert len(fields) >= 5
    assert all(field.source_location for field in fields)
    assert all("建议人工复核" in field.suggested_action for field in fields)


def test_external_review_fields_mask_sensitive_values():
    fields = build_external_review_fields(_single_document_chunks())
    df_text = external_fields_to_dataframe(fields).to_string()
    assert "110101199001011234" not in df_text
    assert "91310000MA1K000001" not in df_text
    assert "****" in df_text


def test_single_document_reports_generate():
    chunks = _single_document_chunks()
    findings = review_single_document(chunks)
    fields = build_external_review_fields(chunks)
    excel_bytes = build_excel_report(findings, fields)
    html = build_html_report(findings, fields, mode_label="单文书字段抽取模式")
    assert excel_bytes[:2] == b"PK"
    assert "待外部复核字段清单" in html
    assert "单文书字段抽取模式" in html
