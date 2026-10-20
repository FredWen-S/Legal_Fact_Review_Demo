from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.storage.audit_log import list_audit_events, save_audit_event
from app.storage.review_history import list_review_history, save_review_history


RAW_DOCUMENT_TEXT = "完整文书正文：2026年2月1日，双方签署《技术服务合同》。"
RAW_PROMPT = "SYSTEM PROMPT: do not store"
RAW_RESPONSE = '{"raw":"full llm response"}'


def _db_text(db_path: Path, table: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()
    return "\n".join(str(value) for row in rows for value in row)


def test_review_history_sanitizes_unexpected_raw_text_fields_before_storage(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"

    save_review_history(
        {
            "review_run_id": "review-1",
            "source_filename": "demo.docx",
            "document_hash": "abc123",
            "mode": "single_document",
            "mode_label": "单文书字段抽取模式",
            "issue_count": 1,
            "severity_high_count": 1,
            "severity_medium_count": 0,
            "severity_low_count": 0,
            "severity_info_count": 0,
            "llm_mode": "mock",
            "llm_fallback_reason": "no_api_key",
            "retrieval_backend": "lexical",
            "retrieval_status_summary": "client:matched",
            "issue_type_summary": {"MISSING_FIELD": 1},
            "export_available": True,
            "notes": "Contact test@example.com phone 13812345678",
            "document_text": RAW_DOCUMENT_TEXT,
            "raw_response": RAW_RESPONSE,
            "prompt": RAW_PROMPT,
        },
        db_path,
    )

    row = list_review_history(path=db_path)[0]
    stored = _db_text(db_path, "review_history")

    assert row.review_run_id == "review-1"
    assert row.issue_count == 1
    assert row.issue_type_summary == {"MISSING_FIELD": 1}
    assert RAW_DOCUMENT_TEXT not in stored
    assert RAW_RESPONSE not in stored
    assert RAW_PROMPT not in stored
    assert "test@example.com" not in stored
    assert "13812345678" not in stored


def test_audit_log_sanitizes_prompt_raw_response_and_traceback(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"
    traceback_text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "app/main.py", line 1, in <module>',
            "RuntimeError: synthetic failure",
        ]
    )

    save_audit_event(
        "run_review_failed",
        review_run_id="review-2",
        source_filename="demo.docx",
        event_summary=traceback_text,
        metadata={
            "prompt": RAW_PROMPT,
            "raw_response": RAW_RESPONSE,
            "document_text": RAW_DOCUMENT_TEXT,
            "normal": "preserved",
            "error": traceback_text,
        },
        path=db_path,
    )

    event = list_audit_events(path=db_path)[0]
    stored = _db_text(db_path, "audit_logs")

    assert event.event_summary == "RuntimeError: synthetic failure"
    assert event.metadata["normal"] == "preserved"
    assert "prompt" not in event.metadata
    assert "raw_response" not in event.metadata
    assert "document_text" not in event.metadata
    assert "Traceback" not in stored
    assert RAW_PROMPT not in stored
    assert RAW_RESPONSE not in stored
    assert RAW_DOCUMENT_TEXT not in stored


def test_audit_metadata_json_remains_parseable_after_sanitizing(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"
    save_audit_event(
        "export_html",
        review_run_id="review-3",
        event_summary="export prepared",
        metadata={"format": "html", "email": "demo@example.com"},
        path=db_path,
    )

    conn = sqlite3.connect(db_path)
    try:
        raw_json = conn.execute("SELECT metadata_json FROM audit_logs").fetchone()[0]
    finally:
        conn.close()

    parsed = json.loads(raw_json)
    assert parsed["format"] == "html"
    assert parsed["email"] != "demo@example.com"
