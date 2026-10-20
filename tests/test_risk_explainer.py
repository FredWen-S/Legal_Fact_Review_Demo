from __future__ import annotations

import json

from app.llm import client as llm_client
from app.llm.risk_explainer import MAX_LLM_FINDINGS, explain_findings, template_explanation
from app.models.schemas import ReviewFinding, TextChunk
from app.reports.excel_report import findings_to_dataframe
from app.reports.html_report import build_html_report
from app.review_engine import review_single_document_result


class _FakeResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._data


def _finding(risk_id: str, risk_type: str = "AMOUNT_INCONSISTENCY", severity: str = "high") -> ReviewFinding:
    return ReviewFinding(
        risk_id=risk_id,
        risk_type=risk_type,
        severity=severity,
        field_name="金额",
        document_value="人民币280,000元 / 人民币260,000元",
        reference_value=None,
        source_location="段落3",
        confidence=0.8,
        reason="Amounts differ.",
        suggested_action="建议人工复核金额。",
    )


CHUNKS = [TextChunk(text="诉讼请求：请求判令被告支付人民币280,000元。", location="段落3")]


def _fake_llm(monkeypatch, explanations: list[dict] | str, captured: list | None = None):
    monkeypatch.setenv("LEGAL_LLM_API_KEY", "test-key")
    content = explanations if isinstance(explanations, str) else json.dumps({"explanations": explanations}, ensure_ascii=False)

    def fake_urlopen(api_request, timeout):
        if captured is not None:
            captured.append(json.loads(api_request.data.decode("utf-8")))
        return _FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)


def test_no_api_key_uses_template_explanations(monkeypatch):
    monkeypatch.delenv("LEGAL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    findings, result = explain_findings([_finding("r1")], CHUNKS)

    assert result.mode == "mock"
    assert result.fallback_reason == "no_api_key"
    assert findings[0].explanation_source == "mock"
    assert findings[0].risk_explanation == template_explanation(findings[0])
    assert "段落3" in findings[0].risk_explanation


def test_llm_explanations_are_attached_per_finding(monkeypatch):
    captured: list = []
    _fake_llm(monkeypatch, [{"risk_id": "r1", "explanation": "诉讼请求金额与事实部分不一致，可能导致请求不明确。"}], captured)

    findings, result = explain_findings([_finding("r1"), _finding("r2", "FORMAT_ERROR", "medium")], CHUNKS)

    assert result.mode == "llm"
    assert result.llm_explained_count == 1
    assert result.explained_count == 2
    assert findings[0].explanation_source == "llm"
    assert findings[0].risk_explanation.startswith("诉讼请求金额")
    # A finding the model skipped keeps a template explanation instead of none.
    assert findings[1].explanation_source == "mock"
    assert findings[1].risk_explanation

    assert len(captured) == 1
    prompt = captured[0]["messages"][1]["content"]
    assert "r1" in prompt and "r2" in prompt and "rule_reason" in prompt


def test_unknown_ids_and_unsafe_text_are_ignored(monkeypatch):
    _fake_llm(
        monkeypatch,
        [
            {"risk_id": "not-a-finding", "explanation": "无关说明"},
            {"risk_id": "r1", "explanation": "系统确认错误，法律上必然无效。"},
        ],
    )

    findings, result = explain_findings([_finding("r1")], CHUNKS)

    assert result.mode == "mock"
    assert "risk_explanation_empty_or_unsafe" in (result.fallback_reason or "")
    assert findings[0].explanation_source == "mock"


def test_malformed_llm_output_falls_back_with_reason(monkeypatch):
    _fake_llm(monkeypatch, "{not-json")

    findings, result = explain_findings([_finding("r1")], CHUNKS)

    assert result.mode == "mock"
    assert "malformed_llm_content_json" in (result.fallback_reason or "")
    assert findings[0].risk_explanation


def test_schema_failure_falls_back_with_reason(monkeypatch):
    _fake_llm(monkeypatch, json.dumps({"items": []}))

    _findings, result = explain_findings([_finding("r1")], CHUNKS)

    assert result.mode == "mock"
    assert "risk_explanation_schema_validation_failure" in (result.fallback_reason or "")


def test_llm_request_is_capped(monkeypatch):
    captured: list = []
    _fake_llm(monkeypatch, [{"risk_id": "r0", "explanation": "说明"}], captured)
    many = [_finding(f"r{index}") for index in range(MAX_LLM_FINDINGS + 5)]

    findings, result = explain_findings(many, CHUNKS)

    prompt = captured[0]["messages"][1]["content"]
    assert f"r{MAX_LLM_FINDINGS - 1}\"" in prompt
    assert f"r{MAX_LLM_FINDINGS}\"" not in prompt
    assert len(findings) == len(many)
    assert all(finding.risk_explanation for finding in findings)
    assert result.llm_explained_count == 1


def test_report_masks_identifiers_in_explanations():
    finding = _finding("r1").model_copy(
        update={"risk_explanation": "信用代码91310115MA1RXH0026与档案不一致。", "explanation_source": "llm"}
    )
    df = findings_to_dataframe([finding])

    assert "Risk Explanation" in df.columns
    assert "91310115MA1RXH0026" not in df.to_string()
    assert df.iloc[0]["Explanation Source"] == "llm"
    assert "Risk Explanations:</strong> 1 by LLM" in build_html_report([finding])


def test_review_result_carries_explanation_metadata(monkeypatch):
    monkeypatch.delenv("LEGAL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    chunks = [
        TextChunk(text="原告：上海星澜智能科技有限公司。", location="段落1"),
        TextChunk(text="依据《合同法》第一百零七条，被告应承担违约责任。", location="段落2"),
    ]

    result = review_single_document_result(chunks)

    assert result.findings
    assert result.risk_explanation is not None
    assert result.risk_explanation.mode == "mock"
    assert result.risk_explanation.explained_count == len(result.findings)
    assert all(finding.risk_explanation for finding in result.findings)
