from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.schemas import (
    KnowledgeContext,
    KnowledgeRetrievalStatus,
    ReviewFinding,
    ReviewResult,
    StructuredExtractionResult,
)
from app.storage.review_history import (
    build_review_history_metadata,
    list_review_history,
    save_review_history,
    stable_document_hash,
)
from app.storage.sqlite_store import get_review_run_detail, save_review_run


SENSITIVE_SENTENCE = "2026年2月1日，双方签署《技术服务合同》。"
RAW_LLM_RESPONSE = '{"full_response":"do not store this"}'


def _finding(severity: str, risk_type: str) -> ReviewFinding:
    return ReviewFinding(
        risk_id=f"{risk_type}-{severity}",
        risk_type=risk_type,
        severity=severity,
        field_name="金额",
        document_value=SENSITIVE_SENTENCE,
        reference_value=None,
        source_location="段落1",
        confidence=0.8,
        reason="字段需要人工复核。",
        suggested_action="建议人工复核该字段。",
    )


def _review_result() -> ReviewResult:
    return ReviewResult(
        findings=[
            _finding("high", "MISSING_FIELD"),
            _finding("medium", "FORMAT_ERROR"),
            _finding("low", "DATE_LOGIC_WARNING"),
        ],
        structured_extraction=StructuredExtractionResult(
            mode="mock",
            model_name="deterministic-mock-extractor",
            raw_response=RAW_LLM_RESPONSE,
            fallback_reason="no_api_key",
        ),
        knowledge_context=KnowledgeContext(
            retrieval_statuses=[
                KnowledgeRetrievalStatus(
                    kb_type="client",
                    status="matched",
                    min_score=3.0,
                    best_score=8.0,
                    best_doc_id="client-demo",
                    match_reason="Best client profile score 8.0 met minimum 3.0.",
                ),
                KnowledgeRetrievalStatus(
                    kb_type="template",
                    status="no_match",
                    min_score=0.5,
                    match_reason="No template KB documents were found.",
                ),
            ]
        ),
    )


def test_empty_review_history_returns_empty_list(tmp_path: Path):
    assert list_review_history(path=tmp_path / "reviews.sqlite") == []


def test_review_history_saves_lightweight_metadata_and_counts(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"
    doc_path = tmp_path / "demo.docx"
    doc_path.write_text(SENSITIVE_SENTENCE, encoding="utf-8")

    document_hash = stable_document_hash(doc_path, "demo.docx")
    record = build_review_history_metadata(
        _review_result(),
        source_filename="demo.docx",
        document_hash=document_hash,
        mode="single_document",
        mode_label="单文书字段抽取模式",
        config_version="v-test",
        document_profile="general",
        review_run_id="review-1",
    )

    history_id = save_review_history(record, db_path)
    rows = list_review_history(limit=5, path=db_path)

    assert rows[0].history_id == history_id
    assert rows[0].source_filename == "demo.docx"
    assert rows[0].document_hash == document_hash
    assert rows[0].issue_count == 3
    assert rows[0].severity_high_count == 1
    assert rows[0].severity_medium_count == 1
    assert rows[0].severity_low_count == 1
    assert rows[0].severity_info_count == 0
    assert rows[0].issue_type_summary == {
        "DATE_LOGIC_WARNING": 1,
        "FORMAT_ERROR": 1,
        "MISSING_FIELD": 1,
    }
    assert rows[0].llm_mode == "mock"
    assert rows[0].llm_fallback_reason == "no_api_key"
    assert rows[0].retrieval_backend == "lexical"
    assert "client:matched" in rows[0].retrieval_status_summary

    conn = sqlite3.connect(db_path)
    try:
        stored = "\n".join(str(value) for row in conn.execute("SELECT * FROM review_history").fetchall() for value in row)
    finally:
        conn.close()
    assert SENSITIVE_SENTENCE not in stored
    assert RAW_LLM_RESPONSE not in stored


def test_document_hash_is_stable_for_same_file_content(tmp_path: Path):
    doc_path = tmp_path / "demo.docx"
    doc_path.write_bytes(b"synthetic document bytes")

    assert stable_document_hash(doc_path, "demo.docx") == stable_document_hash(doc_path, "renamed.docx")


def test_review_run_storage_does_not_keep_raw_llm_response(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"
    review_id = save_review_run(
        [],
        path=db_path,
        structured_extraction=StructuredExtractionResult(mode="llm", raw_response=RAW_LLM_RESPONSE),
    )

    detail = get_review_run_detail(review_id, db_path)

    assert detail is not None
    assert detail.structured_extraction is not None
    assert detail.structured_extraction.raw_response is None
