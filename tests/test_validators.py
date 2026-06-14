from app.extractors.field_extractor import extract_fields
from app.models.schemas import BaseInfoItem, EvidenceItem, TextChunk
from app.review_engine import review_document
from app.validators.consistency_rules import check_amount_inconsistency
from app.validators.evidence_rules import check_evidence_references
from app.validators.format_rules import check_placeholders
from app.validators.source_compare_rules import check_source_mismatch


def test_amount_inconsistency():
    items = extract_fields(
        [
            TextChunk(text="诉讼请求：人民币100,000元。", location="段落1"),
            TextChunk(text="事实与理由：尚欠人民币120,000元。", location="段落2"),
        ]
    )
    findings = check_amount_inconsistency(items)
    assert findings
    assert findings[0].risk_type == "AMOUNT_INCONSISTENCY"


def test_evidence_reference_missing():
    items = extract_fields([TextChunk(text="证据7：付款催告函。", location="段落1")])
    findings = check_evidence_references(items, [EvidenceItem(evidence_no="1", evidence_name="合同")])
    assert findings
    assert findings[0].risk_type == "EVIDENCE_REFERENCE_MISSING"


def test_placeholder_detection():
    items = extract_fields([TextChunk(text="事项：待补充。", location="段落1")])
    findings = check_placeholders(items)
    assert findings
    assert findings[0].source_location == "段落1"


def test_source_mismatch():
    items = extract_fields([TextChunk(text="法定代表人：李四。", location="段落1")])
    base = [BaseInfoItem(field_name="法定代表人", standard_value="张三")]
    findings = check_source_mismatch(items, base)
    assert findings
    assert findings[0].risk_type == "SOURCE_MISMATCH"


def test_review_engine_detects_multiple_sample_like_issues():
    chunks = [
        TextChunk(text="案号：（202X）沪0101民初ABC号", location="段落1"),
        TextChunk(text="原告：上海星河科技有限公司，统一社会信用代码：91310000MA1K000001。", location="段落2"),
        TextChunk(text="法定代表人：李四。", location="段落3"),
        TextChunk(text="2024年5月10日，原告上海星河科技股份有限公司与被告签署合同。", location="段落4"),
        TextChunk(text="履行截止日期为2024年4月30日。", location="段落5"),
        TextChunk(text="诉讼请求：人民币100,000元。", location="段落6"),
        TextChunk(text="事实与理由：尚欠人民币120,000元，证据7证明。", location="段落7"),
        TextChunk(text="其他事项：待补充。", location="段落8"),
    ]
    base = [BaseInfoItem(field_name="法定代表人", standard_value="张三")]
    evidence = [EvidenceItem(evidence_no="1", evidence_name="合同")]
    findings = review_document(chunks, base, evidence)
    assert len(findings) >= 5


def test_all_findings_have_source_location_and_manual_review_action():
    chunks = [TextChunk(text="其他事项：待补充。证据7：催告函。", location="段落1")]
    findings = review_document(chunks, [], [EvidenceItem(evidence_no="1", evidence_name="合同")])
    assert findings
    assert all(finding.source_location for finding in findings)
    assert all("建议人工复核" in finding.suggested_action for finding in findings)
