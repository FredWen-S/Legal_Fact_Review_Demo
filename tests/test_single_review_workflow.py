from __future__ import annotations

from pathlib import Path

from app.config.review_config import default_config
from app.errors import ParseError
from app.models.schemas import KnowledgeContext, ReviewResult, StructuredExtractionResult, TextChunk
from app.workflows import single_review
from app.workflows.single_review import (
    FULL_REVIEW_MODE_LABEL,
    PARTIAL_FULL_REVIEW_WARNING,
    SINGLE_DOCUMENT_MODE_LABEL,
    run_single_review_workflow,
)


def _touch(path: Path) -> Path:
    path.write_text("placeholder", encoding="utf-8")
    return path


def _review_result() -> ReviewResult:
    return ReviewResult(
        structured_extraction=StructuredExtractionResult(
            mode="mock",
            model_name="deterministic-mock-extractor",
            fallback_reason="no_api_key",
        ),
        knowledge_context=KnowledgeContext(),
    )


def test_single_document_workflow_runs(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "demo.docx")
    calls: list[str] = []

    monkeypatch.setattr(single_review, "parse_docx", lambda path: [TextChunk(text="正文", location="段落1")])

    def fake_review(chunks, config=None, document_profile=None):
        calls.append("single")
        assert chunks[0].text == "正文"
        assert document_profile == "civil_complaint"
        return _review_result()

    monkeypatch.setattr(single_review, "review_single_document_result", fake_review)

    result = run_single_review_workflow(
        doc_path,
        config=default_config(),
        document_profile="civil_complaint",
        source_filename="demo.docx",
    )

    assert result.ok
    assert result.mode == "single_document"
    assert result.mode_label == SINGLE_DOCUMENT_MODE_LABEL
    assert result.warnings == []
    assert calls == ["single"]
    assert result.export_context["source_filename"] == "demo.docx"
    assert result.export_context["structured_extraction"].fallback_reason == "no_api_key"
    assert result.history_metadata["source_filename"] == "demo.docx"
    assert result.history_metadata["mode"] == "single_document"
    assert result.history_metadata["llm_mode"] == "mock"
    assert result.history_metadata["llm_fallback_reason"] == "no_api_key"
    assert len(result.history_metadata["document_hash"]) == 64
    assert result.audit_metadata["document_hash"] == result.history_metadata["document_hash"]


def test_full_review_workflow_runs(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "demo.docx")
    base_path = _touch(tmp_path / "base.xlsx")
    evidence_path = _touch(tmp_path / "evidence.xlsx")
    calls: list[str] = []

    monkeypatch.setattr(single_review, "parse_docx", lambda path: [TextChunk(text="正文", location="段落1")])
    monkeypatch.setattr(single_review, "parse_base_info", lambda path: ["base"])
    monkeypatch.setattr(single_review, "parse_evidence_index", lambda path: ["evidence"])

    def fake_review(chunks, base_info, evidence_index, config=None, document_profile=None):
        calls.append("full")
        assert base_info == ["base"]
        assert evidence_index == ["evidence"]
        return _review_result()

    monkeypatch.setattr(single_review, "review_document_result", fake_review)

    result = run_single_review_workflow(
        doc_path,
        base_info_path=base_path,
        evidence_index_path=evidence_path,
        config=default_config(),
        source_filename="demo.docx",
    )

    assert result.ok
    assert result.mode == "full_review"
    assert result.mode_label == FULL_REVIEW_MODE_LABEL
    assert result.warnings == []
    assert calls == ["full"]


def test_partial_base_info_warns_and_runs_single_document(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "demo.docx")
    base_path = _touch(tmp_path / "base.xlsx")
    calls: list[str] = []

    monkeypatch.setattr(single_review, "parse_docx", lambda path: [TextChunk(text="正文", location="段落1")])
    monkeypatch.setattr(single_review, "parse_base_info", lambda path: (_ for _ in ()).throw(AssertionError("base should not be parsed")))

    def fake_review(chunks, config=None, document_profile=None):
        calls.append("single")
        return _review_result()

    monkeypatch.setattr(single_review, "review_single_document_result", fake_review)

    result = run_single_review_workflow(doc_path, base_info_path=base_path, config=default_config())

    assert result.ok
    assert result.mode == "single_document"
    assert PARTIAL_FULL_REVIEW_WARNING in result.warnings
    assert calls == ["single"]


def test_partial_evidence_index_warns_and_runs_single_document(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "demo.docx")
    evidence_path = _touch(tmp_path / "evidence.xlsx")
    calls: list[str] = []

    monkeypatch.setattr(single_review, "parse_docx", lambda path: [TextChunk(text="正文", location="段落1")])
    monkeypatch.setattr(single_review, "parse_evidence_index", lambda path: (_ for _ in ()).throw(AssertionError("evidence should not be parsed")))
    monkeypatch.setattr(single_review, "review_single_document_result", lambda chunks, config=None, document_profile=None: calls.append("single") or _review_result())

    result = run_single_review_workflow(doc_path, evidence_index_path=evidence_path, config=default_config())

    assert result.ok
    assert result.mode == "single_document"
    assert PARTIAL_FULL_REVIEW_WARNING in result.warnings
    assert calls == ["single"]


def test_missing_document_returns_error(tmp_path: Path):
    result = run_single_review_workflow(tmp_path / "missing.docx", config=default_config())

    assert not result.ok
    assert result.review_result is None
    assert result.errors
    assert "主文书路径不存在" in result.errors[0]


def test_parser_failure_returns_error(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "bad.docx")

    def fail_parse(path):
        raise ParseError("DOCX 解析失败。")

    monkeypatch.setattr(single_review, "parse_docx", fail_parse)

    result = run_single_review_workflow(doc_path, config=default_config())

    assert not result.ok
    assert result.review_result is None
    assert result.errors == ["DOCX 解析失败。"]
    assert result.audit_metadata["source_filename"] == "bad.docx"
    assert result.audit_metadata["error"] == "DOCX 解析失败。"


def test_full_review_base_info_parse_failure_returns_error(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "demo.docx")
    base_path = _touch(tmp_path / "bad_base.xlsx")
    evidence_path = _touch(tmp_path / "evidence.xlsx")

    monkeypatch.setattr(single_review, "parse_docx", lambda path: [TextChunk(text="正文", location="段落1")])
    monkeypatch.setattr(single_review, "parse_base_info", lambda path: (_ for _ in ()).throw(ParseError("基础信息表解析失败。")))
    monkeypatch.setattr(single_review, "parse_evidence_index", lambda path: ["evidence"])

    result = run_single_review_workflow(
        doc_path,
        base_info_path=base_path,
        evidence_index_path=evidence_path,
        config=default_config(),
    )

    assert not result.ok
    assert result.mode == "full_review"
    assert result.errors == ["基础信息表解析失败。"]


def test_review_engine_failure_returns_error(monkeypatch, tmp_path: Path):
    doc_path = _touch(tmp_path / "demo.docx")

    monkeypatch.setattr(single_review, "parse_docx", lambda path: [TextChunk(text="正文", location="段落1")])
    monkeypatch.setattr(single_review, "review_single_document_result", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = run_single_review_workflow(doc_path, config=default_config())

    assert not result.ok
    assert result.errors == ["复核引擎执行失败。请检查输入文件内容，或使用示例数据验证环境是否正常。"]
    assert result.export_context["mode_label"] == SINGLE_DOCUMENT_MODE_LABEL
    assert result.audit_metadata["mode"] == "single_document"
    assert "error" in result.audit_metadata
