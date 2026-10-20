from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.history import AuditLogEntry
from app.privacy.policy import PrivacyPolicy, default_privacy_policy
from app.privacy.redaction import redact_text, sanitize_error, sanitize_metadata
from app.storage.sqlite_store import init_db


MAX_SUMMARY_LENGTH = 500
MAX_METADATA_STRING_LENGTH = 500


def save_audit_event(
    event_type: str,
    *,
    review_run_id: str | None = None,
    source_filename: str | None = None,
    event_summary: str = "",
    metadata: dict[str, Any] | None = None,
    path: str | Path = "data/review_runs.sqlite",
    privacy_policy: PrivacyPolicy | None = None,
) -> int:
    policy = privacy_policy or default_privacy_policy()
    entry = AuditLogEntry(
        event_type=_compact_text(event_type, 120),
        review_run_id=redact_text(_compact_text(review_run_id, 120), policy) if review_run_id else None,
        source_filename=redact_text(_compact_text(source_filename, 260), policy) if source_filename else None,
        event_summary=sanitize_error(event_summary, policy),
        metadata=sanitize_metadata(metadata or {}, policy),
    )
    conn = init_db(path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (
                created_at, event_type, review_run_id, source_filename, event_summary, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.created_at.isoformat(timespec="seconds"),
                entry.event_type,
                entry.review_run_id,
                entry.source_filename,
                entry.event_summary,
                json.dumps(entry.metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_audit_events(
    limit: int = 50,
    *,
    review_run_id: str | None = None,
    path: str | Path = "data/review_runs.sqlite",
) -> list[AuditLogEntry]:
    conn = init_db(path)
    try:
        if review_run_id:
            rows = conn.execute(
                """
                SELECT id, created_at, event_type, review_run_id, source_filename, event_summary, metadata_json
                FROM audit_logs
                WHERE review_run_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (review_run_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, created_at, event_type, review_run_id, source_filename, event_summary, metadata_json
                FROM audit_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    return [_audit_from_row(row) for row in rows]


def _audit_from_row(row) -> AuditLogEntry:
    try:
        metadata = json.loads(row[6] or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return AuditLogEntry(
        audit_id=row[0],
        created_at=datetime.fromisoformat(row[1]),
        event_type=row[2],
        review_run_id=row[3],
        source_filename=row[4],
        event_summary=row[5],
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _compact_text(value: str | None, max_length: int) -> str:
    text = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
