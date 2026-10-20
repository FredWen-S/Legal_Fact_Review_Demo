from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.history import ReviewHistoryRecord
from app.models.schemas import KnowledgeContext, ReviewResult
from app.privacy.policy import PrivacyPolicy, default_privacy_policy
from app.privacy.redaction import redact_text, sanitize_metadata
from app.storage.sqlite_store import init_db


def stable_document_hash(document_path: str | Path, source_filename: str | None = None) -> str:
    path = Path(document_path)
    digest = hashlib.sha256()
    if path.exists() and path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    fallback = f"{source_filename or path.name}|missing|0"
    digest.update(fallback.encode("utf-8"))
    return digest.hexdigest()


def build_review_history_metadata(
    review_result: ReviewResult,
    *,
    source_filename: str | None,
    document_hash: str,
    mode: str,
    mode_label: str,
    config_version: str | None = None,
    document_profile: str | None = None,
    review_run_id: str | None = None,
    export_available: bool = True,
    notes: str | None = None,
) -> ReviewHistoryRecord:
    severity_counts = review_result.severity_counts()
    structured = review_result.structured_extraction
    issue_type_summary = Counter(str(finding.risk_type) for finding in review_result.findings)
    knowledge_context = review_result.knowledge_context

    return ReviewHistoryRecord(
        review_run_id=review_run_id,
        source_filename=_compact_text(source_filename, 260) if source_filename else None,
        document_hash=document_hash,
        mode=mode,
        mode_label=mode_label,
        config_version=_compact_text(config_version, 120) if config_version else None,
        document_profile=_compact_text(document_profile, 120) if document_profile else None,
        issue_count=len(review_result.findings),
        severity_high_count=severity_counts["HIGH"],
        severity_medium_count=severity_counts["MEDIUM"],
        severity_low_count=severity_counts["LOW"],
        severity_info_count=0,
        llm_mode=structured.mode if structured else "not_available",
        llm_fallback_reason=_compact_text(structured.fallback_reason, 300) if structured and structured.fallback_reason else None,
        retrieval_backend=_infer_retrieval_backend(knowledge_context),
        retrieval_status_summary=_summarize_retrieval_statuses(knowledge_context),
        issue_type_summary=dict(sorted(issue_type_summary.items())),
        export_available=export_available,
        notes=_compact_text(notes, 500) if notes else None,
    )


def save_review_history(
    record: ReviewHistoryRecord | dict[str, Any],
    path: str | Path = "data/review_runs.sqlite",
    privacy_policy: PrivacyPolicy | None = None,
) -> int:
    policy = privacy_policy or default_privacy_policy()
    payload = record.model_dump(mode="json") if isinstance(record, ReviewHistoryRecord) else dict(record)
    payload = sanitize_metadata(payload, policy)
    entry = ReviewHistoryRecord(**payload)
    conn = init_db(path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO review_history (
                created_at, review_run_id, source_filename, document_hash, mode, mode_label,
                config_version, document_profile, issue_count, severity_high_count,
                severity_medium_count, severity_low_count, severity_info_count, llm_mode,
                llm_fallback_reason, retrieval_backend, retrieval_status_summary,
                issue_type_summary_json, export_available, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.created_at.isoformat(timespec="seconds"),
                entry.review_run_id,
                entry.source_filename,
                entry.document_hash,
                entry.mode,
                entry.mode_label,
                entry.config_version,
                entry.document_profile,
                entry.issue_count,
                entry.severity_high_count,
                entry.severity_medium_count,
                entry.severity_low_count,
                entry.severity_info_count,
                entry.llm_mode,
                entry.llm_fallback_reason,
                entry.retrieval_backend,
                entry.retrieval_status_summary,
                json.dumps(entry.issue_type_summary, ensure_ascii=False, sort_keys=True),
                1 if entry.export_available else 0,
                entry.notes,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_review_history(
    limit: int = 10,
    path: str | Path = "data/review_runs.sqlite",
) -> list[ReviewHistoryRecord]:
    conn = init_db(path)
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, review_run_id, source_filename, document_hash, mode,
                   mode_label, config_version, document_profile, issue_count,
                   severity_high_count, severity_medium_count, severity_low_count,
                   severity_info_count, llm_mode, llm_fallback_reason, retrieval_backend,
                   retrieval_status_summary, issue_type_summary_json, export_available, notes
            FROM review_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [_history_from_row(row) for row in rows]


def _history_from_row(row) -> ReviewHistoryRecord:
    try:
        issue_type_summary = json.loads(row[18] or "{}")
    except json.JSONDecodeError:
        issue_type_summary = {}
    return ReviewHistoryRecord(
        history_id=row[0],
        created_at=datetime.fromisoformat(row[1]),
        review_run_id=row[2],
        source_filename=row[3],
        document_hash=row[4],
        mode=row[5],
        mode_label=row[6],
        config_version=row[7],
        document_profile=row[8],
        issue_count=row[9],
        severity_high_count=row[10],
        severity_medium_count=row[11],
        severity_low_count=row[12],
        severity_info_count=row[13],
        llm_mode=row[14],
        llm_fallback_reason=row[15],
        retrieval_backend=row[16],
        retrieval_status_summary=row[17],
        issue_type_summary=issue_type_summary if isinstance(issue_type_summary, dict) else {},
        export_available=bool(row[19]),
        notes=row[20],
    )


def _infer_retrieval_backend(knowledge_context: KnowledgeContext | None) -> str:
    if knowledge_context is None:
        return "not_available"
    reasons = " ".join(
        [status.match_reason for status in knowledge_context.retrieval_statuses]
        + ([knowledge_context.client_profile.match_reason] if knowledge_context.client_profile else [])
        + [match.match_reason for match in knowledge_context.templates]
        + [match.match_reason for match in knowledge_context.clauses]
    ).lower()
    if "fallback_lexical" in reasons:
        return "embedding_fallback_lexical"
    if "embedding" in reasons:
        return "embedding"
    return "lexical"


def _summarize_retrieval_statuses(knowledge_context: KnowledgeContext | None) -> str:
    if knowledge_context is None or not knowledge_context.retrieval_statuses:
        return "not_available"
    parts: list[str] = []
    for status in knowledge_context.retrieval_statuses:
        detail = f"{status.kb_type}:{status.status}"
        if status.best_score is not None:
            detail += f"(best_score={status.best_score})"
        parts.append(detail)
    return _compact_text("; ".join(parts), 1000)


def _compact_text(value: str | None, max_length: int) -> str:
    text = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return redact_text(text[: max_length - 3] + "...")
