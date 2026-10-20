import json
from pathlib import Path
from urllib import error

from app.extractors import llm_extractor
from app.extractors.llm_extractor import extract_structured_entities
from app.models.schemas import TextChunk
from app.parsers.docx_parser import parse_docx
from app.rag.retrieval import build_knowledge_context
from app.review_engine import review_single_document_result
from app.validators.rag_rules import check_knowledge_alignment


class _FakeResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._data


def _rag_demo_chunks() -> list[TextChunk]:
    return [
        TextChunk(
            text="甲方：上海星何科技股份有限公司，统一社会信用代码：91310000MA1K000001。",
            location="段落1",
        ),
        TextChunk(text="法定代表人：张明远。注册地址：上海市浦东新区星港路88号12层。", location="段落2"),
        TextChunk(text="合同编号：HT-2024-SH-009。", location="段落3"),
        TextChunk(text="第一条 服务内容", location="段落4"),
        TextChunk(text="第三条 付款安排", location="段落5"),
        TextChunk(text="乙方应按项目验收后开具发票。", location="段落6"),
    ]


def test_document_parsing_sample_docx_returns_chunks():
    sample_doc = Path("app/sample_data/test_cases/case_09_custom_rules_profile/contract_review.docx")
    chunks = parse_docx(sample_doc)
    assert chunks
    assert all(chunk.text for chunk in chunks)


def test_mock_structured_extraction_extracts_required_entities():
    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=False)
    assert extraction.mode == "mock"
    assert "91310000MA1K000001" in extraction.values("credit_code")
    assert "张明远" in extraction.values("legal_representative")
    assert "HT-2024-SH-009" in extraction.values("contract_id")


def test_no_api_key_uses_mock_with_fallback_reason(monkeypatch):
    monkeypatch.delenv("LEGAL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=True)

    assert extraction.mode == "mock"
    assert extraction.fallback_reason == "no_api_key"


def test_valid_llm_json_passes_schema_validation(monkeypatch):
    monkeypatch.setenv("LEGAL_LLM_API_KEY", "test-key")
    llm_payload = {
        "parties": [{"value": "上海星何科技股份有限公司", "role": "甲方"}],
        "company_names": [{"value": "上海星何科技股份有限公司"}],
        "credit_codes": [{"value": "91310000MA1K000001"}],
        "legal_representatives": [{"value": "张明远"}],
        "registered_addresses": [{"value": "上海市浦东新区星港路88号12层"}],
        "dates": [],
        "amounts": [],
        "contract_ids": [{"value": "HT-2024-SH-009"}],
    }

    def fake_urlopen(_request, timeout):
        return _FakeResponse({"choices": [{"message": {"content": json.dumps(llm_payload, ensure_ascii=False)}}]})

    monkeypatch.setattr(llm_extractor.request, "urlopen", fake_urlopen)

    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=True)

    assert extraction.mode == "llm"
    assert extraction.fallback_reason is None
    assert "91310000MA1K000001" in extraction.values("credit_code")


def test_malformed_llm_json_falls_back_with_reason(monkeypatch):
    monkeypatch.setenv("LEGAL_LLM_API_KEY", "test-key")

    def fake_urlopen(_request, timeout):
        return _FakeResponse({"choices": [{"message": {"content": "{not-json"}}]})

    monkeypatch.setattr(llm_extractor.request, "urlopen", fake_urlopen)

    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=True)

    assert extraction.mode == "mock"
    assert extraction.fallback_reason
    assert "malformed_llm_content_json" in extraction.fallback_reason


def test_llm_schema_validation_failure_falls_back_with_reason(monkeypatch):
    monkeypatch.setenv("LEGAL_LLM_API_KEY", "test-key")

    def fake_urlopen(_request, timeout):
        return _FakeResponse({"choices": [{"message": {"content": json.dumps({"parties": []})}}]})

    monkeypatch.setattr(llm_extractor.request, "urlopen", fake_urlopen)

    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=True)

    assert extraction.mode == "mock"
    assert extraction.fallback_reason
    assert "llm_schema_validation_failure" in extraction.fallback_reason


def test_llm_api_failure_and_timeout_fallback_reason(monkeypatch):
    monkeypatch.setenv("LEGAL_LLM_API_KEY", "test-key")

    def fail_urlopen(_request, timeout):
        raise error.URLError("network down")

    monkeypatch.setattr(llm_extractor.request, "urlopen", fail_urlopen)
    failure = extract_structured_entities(_rag_demo_chunks(), force_llm=True)
    assert failure.mode == "mock"
    assert failure.fallback_reason and "api_error" in failure.fallback_reason

    def timeout_urlopen(_request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(llm_extractor.request, "urlopen", timeout_urlopen)
    timeout = extract_structured_entities(_rag_demo_chunks(), force_llm=True)
    assert timeout.mode == "mock"
    assert timeout.fallback_reason and "api_timeout" in timeout.fallback_reason


def test_rag_retrieval_returns_matching_client_and_template():
    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=False)
    context = build_knowledge_context(_rag_demo_chunks(), extraction)
    assert context.client_profile is not None
    assert context.client_profile.title == "上海星河科技股份有限公司"
    assert context.client_profile.match_reason
    assert context.status_for("client").status == "matched"
    assert any(match.kb_type == "template" for match in context.templates)


def test_empty_kb_returns_no_match_status(tmp_path: Path):
    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=False)
    context = build_knowledge_context(_rag_demo_chunks(), extraction, kb_root=tmp_path)

    assert context.client_profile is None
    assert context.templates == []
    assert context.status_for("client").status == "no_match"
    assert "KB directory not found" in context.status_for("client").match_reason


def test_broken_kb_json_returns_explainable_no_match(tmp_path: Path):
    clients = tmp_path / "clients"
    clients.mkdir()
    (clients / "broken.json").write_text("{not-json", encoding="utf-8")

    extraction = extract_structured_entities(_rag_demo_chunks(), force_llm=False)
    context = build_knowledge_context(_rag_demo_chunks(), extraction, kb_root=tmp_path)

    assert context.client_profile is None
    assert context.status_for("client").status == "no_match"
    assert "Invalid JSON" in context.status_for("client").match_reason


def test_low_score_client_candidate_does_not_emit_high_rag_mismatch(tmp_path: Path):
    clients = tmp_path / "clients"
    clients.mkdir()
    (clients / "generic.json").write_text(
        json.dumps(
            {
                "id": "generic-client",
                "title": "通用合同客户",
                "legal_name": "完全不同客户有限公司",
                "credit_code": "000000000000000000",
                "keywords": ["合同"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chunks = [TextChunk(text="合同文本只提到付款安排。", location="段落1")]
    extraction = extract_structured_entities(chunks, force_llm=False)
    context = build_knowledge_context(chunks, extraction, kb_root=tmp_path, min_scores={"client": 5.0})

    assert context.client_profile is None
    assert context.status_for("client").status in {"low_confidence_match", "no_match"}
    findings = check_knowledge_alignment(chunks, extraction, context)
    assert not any(finding.risk_type == "CLIENT_PROFILE_MISMATCH" and finding.severity == "high" for finding in findings)


def test_missing_required_clause_file_does_not_break_retrieval(tmp_path: Path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "template.json").write_text(
        json.dumps(
            {
                "id": "template-with-missing-clause",
                "title": "合同模板",
                "summary": "合同模板",
                "keywords": ["合同模板"],
                "required_clause_ids": ["missing-clause"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chunks = [TextChunk(text="合同模板", location="段落1")]
    extraction = extract_structured_entities(chunks, force_llm=False)
    context = build_knowledge_context(chunks, extraction, kb_root=tmp_path)

    assert context.status_for("template").status == "matched"
    assert context.clauses == []
    assert context.status_for("clause").status == "no_match"


def test_rule_checks_surface_spelling_numbering_and_clause_gaps():
    result = review_single_document_result(_rag_demo_chunks(), document_profile="contract_review")
    issue_types = {finding.risk_type for finding in result.findings}
    assert "SPELLING_VARIATION" in issue_types or "CLIENT_PROFILE_MISMATCH" in issue_types
    assert "CLAUSE_NUMBERING_ERROR" in issue_types
    assert "MISSING_STANDARD_CLAUSE" in issue_types


def test_issue_severity_counts_match_findings():
    result = review_single_document_result(_rag_demo_chunks(), document_profile="contract_review")
    counts = result.severity_counts()
    assert set(counts) == {"HIGH", "MEDIUM", "LOW"}
    assert sum(counts.values()) == len(result.findings)
