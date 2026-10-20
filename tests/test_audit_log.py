from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.storage.audit_log import list_audit_events, save_audit_event


def test_audit_log_writes_run_review_succeeded(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"

    event_id = save_audit_event(
        "run_review_succeeded",
        review_run_id="review-1",
        source_filename="demo.docx",
        event_summary="Single review succeeded.",
        metadata={"finding_count": 2, "retrieval_backend": "lexical"},
        path=db_path,
    )
    events = list_audit_events(path=db_path)

    assert events[0].audit_id == event_id
    assert events[0].event_type == "run_review_succeeded"
    assert events[0].review_run_id == "review-1"
    assert events[0].metadata["finding_count"] == 2


def test_audit_log_writes_run_review_failed_with_short_error(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"
    traceback_text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "app/main.py", line 1, in <module>',
            "RuntimeError: synthetic parser failed",
        ]
    )

    save_audit_event(
        "run_review_failed",
        source_filename="bad.docx",
        event_summary=traceback_text,
        metadata={"error": traceback_text, "large": "x" * 1000},
        path=db_path,
    )
    event = list_audit_events(path=db_path)[0]

    assert "Traceback" not in event.event_summary
    assert event.event_summary == "RuntimeError: synthetic parser failed"
    assert "Traceback" not in json.dumps(event.metadata, ensure_ascii=False)
    assert len(event.metadata["large"]) <= 500


def test_audit_log_writes_export_event_and_metadata_json_is_parseable(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"

    save_audit_event(
        "export_zip",
        review_run_id="review-2",
        source_filename="demo.docx",
        event_summary="export_zip prepared for Streamlit download.",
        metadata={"format": "zip", "byte_size": 128, "prepared_in_ui": True},
        path=db_path,
    )

    conn = sqlite3.connect(db_path)
    try:
        raw_metadata = conn.execute("SELECT metadata_json FROM audit_logs").fetchone()[0]
    finally:
        conn.close()
    parsed = json.loads(raw_metadata)
    assert parsed["format"] == "zip"
    assert parsed["prepared_in_ui"] is True

    events = list_audit_events(review_run_id="review-2", path=db_path)
    assert events[0].event_type == "export_zip"


def test_audit_log_supports_required_event_types(tmp_path: Path):
    db_path = tmp_path / "reviews.sqlite"
    event_types = [
        "run_review_started",
        "run_review_succeeded",
        "run_review_failed",
        "export_excel",
        "export_html",
        "export_docx",
        "export_zip",
    ]

    for event_type in event_types:
        save_audit_event(event_type, event_summary=f"{event_type} summary", path=db_path)

    stored = {event.event_type for event in list_audit_events(limit=20, path=db_path)}
    assert set(event_types).issubset(stored)
