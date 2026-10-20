from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.models.schemas import CaseDocument, CaseWorkspace, ExtractedReviewField, ManualReviewRecord, ReviewFinding, ReviewRunDetail, ReviewRunSummary, RuleConfigHistory
from app.utils import stable_id


def init_db(path: str | Path = "data/review_runs.sqlite") -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            finding_count INTEGER NOT NULL,
            findings_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_workspaces (
            case_id TEXT PRIMARY KEY,
            case_name TEXT NOT NULL,
            internal_case_no TEXT,
            client_name TEXT,
            counterparty_name TEXT,
            case_type TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS case_documents (
            document_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL,
            document_role TEXT,
            note TEXT,
            FOREIGN KEY(case_id) REFERENCES case_workspaces(case_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_review_records (
            record_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL,
            field_id TEXT NOT NULL,
            field_type TEXT NOT NULL,
            extracted_value TEXT NOT NULL,
            confirmed_value TEXT,
            review_status TEXT NOT NULL,
            review_source TEXT,
            reviewer_note TEXT,
            source_location TEXT NOT NULL,
            reviewed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rule_config_history (
            config_history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_version TEXT NOT NULL,
            saved_at TEXT NOT NULL,
            change_note TEXT,
            backup_path TEXT,
            active_config_path TEXT NOT NULL
        )
        """
    )
    _ensure_column(conn, "review_runs", "case_id", "TEXT")
    _ensure_column(conn, "review_runs", "document_id", "TEXT")
    _ensure_column(conn, "review_runs", "file_name", "TEXT")
    _ensure_column(conn, "review_runs", "mode_label", "TEXT")
    _ensure_column(conn, "review_runs", "high_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "review_runs", "medium_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "review_runs", "low_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "review_runs", "external_field_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "review_runs", "external_fields_json", "TEXT DEFAULT '[]'")
    _ensure_column(conn, "review_runs", "config_version", "TEXT")
    _ensure_column(conn, "review_runs", "document_profile", "TEXT")
    conn.commit()
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_case_workspace(
    case_name: str,
    internal_case_no: str | None = None,
    client_name: str | None = None,
    counterparty_name: str | None = None,
    case_type: str | None = None,
    note: str | None = None,
    path: str | Path = "data/review_runs.sqlite",
) -> CaseWorkspace:
    conn = init_db(path)
    try:
        now = datetime.now()
        case_id = stable_id("case", case_name, internal_case_no, now.isoformat(timespec="microseconds"))
        case = CaseWorkspace(
            case_id=case_id,
            case_name=case_name,
            internal_case_no=internal_case_no or None,
            client_name=client_name or None,
            counterparty_name=counterparty_name or None,
            case_type=case_type or None,
            note=note or None,
            created_at=now,
            updated_at=now,
        )
        conn.execute(
            """
            INSERT INTO case_workspaces (
                case_id, case_name, internal_case_no, client_name, counterparty_name,
                case_type, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.case_id,
                case.case_name,
                case.internal_case_no,
                case.client_name,
                case.counterparty_name,
                case.case_type,
                case.note,
                case.created_at.isoformat(timespec="seconds"),
                case.updated_at.isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return case
    finally:
        conn.close()


def list_case_workspaces(path: str | Path = "data/review_runs.sqlite") -> list[CaseWorkspace]:
    conn = init_db(path)
    try:
        rows = conn.execute(
            """
            SELECT case_id, case_name, internal_case_no, client_name, counterparty_name,
                   case_type, note, created_at, updated_at
            FROM case_workspaces
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [_case_from_row(row) for row in rows]


def get_case_workspace(case_id: str, path: str | Path = "data/review_runs.sqlite") -> CaseWorkspace | None:
    conn = init_db(path)
    try:
        row = conn.execute(
            """
            SELECT case_id, case_name, internal_case_no, client_name, counterparty_name,
                   case_type, note, created_at, updated_at
            FROM case_workspaces
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
    finally:
        conn.close()
    return _case_from_row(row) if row else None


def delete_case_workspace(case_id: str, path: str | Path = "data/review_runs.sqlite") -> None:
    conn = init_db(path)
    try:
        conn.execute("DELETE FROM manual_review_records WHERE review_id IN (SELECT 'review-' || id FROM review_runs WHERE case_id = ?)", (case_id,))
        conn.execute("DELETE FROM review_runs WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM case_documents WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM case_workspaces WHERE case_id = ?", (case_id,))
        conn.commit()
    finally:
        conn.close()


def save_case_document(
    case_id: str,
    file_name: str,
    file_type: str,
    file_size: int,
    document_role: str | None = None,
    note: str | None = None,
    path: str | Path = "data/review_runs.sqlite",
) -> CaseDocument:
    conn = init_db(path)
    try:
        now = datetime.now()
        document_id = stable_id("doc", case_id, file_name, file_size, now.isoformat(timespec="microseconds"))
        document = CaseDocument(
            document_id=document_id,
            case_id=case_id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            uploaded_at=now,
            document_role=document_role or None,
            note=note or None,
        )
        conn.execute(
            """
            INSERT INTO case_documents (
                document_id, case_id, file_name, file_type, file_size,
                uploaded_at, document_role, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.document_id,
                document.case_id,
                document.file_name,
                document.file_type,
                document.file_size,
                document.uploaded_at.isoformat(timespec="seconds"),
                document.document_role,
                document.note,
            ),
        )
        conn.execute("UPDATE case_workspaces SET updated_at = ? WHERE case_id = ?", (now.isoformat(timespec="seconds"), case_id))
        conn.commit()
        return document
    finally:
        conn.close()


def list_case_documents(case_id: str, path: str | Path = "data/review_runs.sqlite") -> list[CaseDocument]:
    conn = init_db(path)
    try:
        rows = conn.execute(
            """
            SELECT document_id, case_id, file_name, file_type, file_size, uploaded_at, document_role, note
            FROM case_documents
            WHERE case_id = ?
            ORDER BY uploaded_at DESC
            """,
            (case_id,),
        ).fetchall()
    finally:
        conn.close()
    return [_document_from_row(row) for row in rows]


def save_review_run(
    findings: list[ReviewFinding],
    path: str | Path = "data/review_runs.sqlite",
    external_fields: list[ExtractedReviewField] | None = None,
    case_id: str | None = None,
    document_id: str | None = None,
    file_name: str | None = None,
    mode_label: str = "完整复核模式",
    config_version: str | None = None,
    document_profile: str | None = None,
) -> str:
    conn = init_db(path)
    try:
        created_at = datetime.now().isoformat(timespec="seconds")
        high = sum(1 for finding in findings if finding.severity == "high")
        medium = sum(1 for finding in findings if finding.severity == "medium")
        low = sum(1 for finding in findings if finding.severity == "low")
        fields = _sanitize_external_fields_for_storage(external_fields or [])
        cursor = conn.execute(
            """
            INSERT INTO review_runs (
                created_at, finding_count, findings_json, case_id, document_id, file_name,
                mode_label, high_count, medium_count, low_count, external_field_count, external_fields_json,
                config_version, document_profile
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                len(findings),
                json.dumps([finding.model_dump() for finding in findings], ensure_ascii=False),
                case_id,
                document_id,
                file_name,
                mode_label,
                high,
                medium,
                low,
                len(fields),
                json.dumps([field.model_dump() for field in fields], ensure_ascii=False),
                config_version,
                document_profile,
            ),
        )
        if case_id:
            conn.execute("UPDATE case_workspaces SET updated_at = ? WHERE case_id = ?", (created_at, case_id))
        conn.commit()
        return f"review-{cursor.lastrowid}"
    finally:
        conn.close()


def list_review_runs(case_id: str | None = None, path: str | Path = "data/review_runs.sqlite") -> list[ReviewRunSummary]:
    conn = init_db(path)
    try:
        where = "WHERE r.case_id = ?" if case_id else ""
        params = (case_id,) if case_id else ()
        rows = conn.execute(
            f"""
            SELECT 'review-' || r.id AS review_id, r.case_id, c.case_name, r.document_id, r.file_name,
                   COALESCE(r.mode_label, '完整复核模式') AS mode_label,
                   r.finding_count, COALESCE(r.high_count, 0), COALESCE(r.medium_count, 0),
                   COALESCE(r.low_count, 0), COALESCE(r.external_field_count, 0),
                   COUNT(m.record_id) AS manual_record_count, COALESCE(r.config_version, ''), COALESCE(r.document_profile, ''), r.created_at
            FROM review_runs r
            LEFT JOIN case_workspaces c ON r.case_id = c.case_id
            LEFT JOIN manual_review_records m ON m.review_id = 'review-' || r.id
            {where}
            GROUP BY r.id
            ORDER BY r.created_at DESC
            """,
            params,
        ).fetchall()
    finally:
        conn.close()
    return [_summary_from_row(row) for row in rows]


def get_review_run_detail(review_id: str, path: str | Path = "data/review_runs.sqlite") -> ReviewRunDetail | None:
    numeric_id = _numeric_review_id(review_id)
    conn = init_db(path)
    try:
        row = conn.execute(
            """
            SELECT 'review-' || r.id AS review_id, r.case_id, c.case_name, r.document_id, r.file_name,
                   COALESCE(r.mode_label, '完整复核模式') AS mode_label,
                   r.finding_count, COALESCE(r.high_count, 0), COALESCE(r.medium_count, 0),
                   COALESCE(r.low_count, 0), COALESCE(r.external_field_count, 0),
                   COUNT(m.record_id) AS manual_record_count, COALESCE(r.config_version, ''), COALESCE(r.document_profile, ''), r.created_at,
                   r.findings_json, COALESCE(r.external_fields_json, '[]')
            FROM review_runs r
            LEFT JOIN case_workspaces c ON r.case_id = c.case_id
            LEFT JOIN manual_review_records m ON m.review_id = 'review-' || r.id
            WHERE r.id = ?
            GROUP BY r.id
            """,
            (numeric_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    summary = _summary_from_row(row[:15])
    findings = [ReviewFinding(**item) for item in json.loads(row[15] or "[]")]
    external_fields = [ExtractedReviewField(**item) for item in json.loads(row[16] or "[]")]
    manual_records = fetch_manual_review_records(review_id, path)
    return ReviewRunDetail(**summary.model_dump(), findings=findings, external_fields=external_fields, manual_records=manual_records)


def delete_review_run(review_id: str, path: str | Path = "data/review_runs.sqlite") -> None:
    numeric_id = _numeric_review_id(review_id)
    conn = init_db(path)
    try:
        conn.execute("DELETE FROM manual_review_records WHERE review_id = ?", (review_id,))
        conn.execute("DELETE FROM review_runs WHERE id = ?", (numeric_id,))
        conn.commit()
    finally:
        conn.close()


def save_rule_config_history(
    config_version: str,
    active_config_path: str,
    change_note: str | None = None,
    backup_path: str | None = None,
    path: str | Path = "data/review_runs.sqlite",
) -> int:
    conn = init_db(path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO rule_config_history (config_version, saved_at, change_note, backup_path, active_config_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (config_version, datetime.now().isoformat(timespec="seconds"), change_note, backup_path, active_config_path),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_rule_config_history(limit: int = 10, path: str | Path = "data/review_runs.sqlite") -> list[RuleConfigHistory]:
    conn = init_db(path)
    try:
        rows = conn.execute(
            """
            SELECT config_history_id, config_version, saved_at, change_note, backup_path, active_config_path
            FROM rule_config_history
            ORDER BY config_history_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        RuleConfigHistory(
            config_history_id=row[0],
            config_version=row[1],
            saved_at=datetime.fromisoformat(row[2]),
            change_note=row[3],
            backup_path=row[4],
            active_config_path=row[5],
        )
        for row in rows
    ]


def save_manual_review_records(
    records: list[ManualReviewRecord],
    path: str | Path = "data/review_runs.sqlite",
) -> None:
    conn = init_db(path)
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO manual_review_records (
                record_id, review_id, field_id, field_type, extracted_value, confirmed_value,
                review_status, review_source, reviewer_note, source_location, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.record_id,
                    record.review_id,
                    record.field_id,
                    record.field_type,
                    record.extracted_value,
                    record.confirmed_value,
                    record.review_status,
                    record.review_source,
                    record.reviewer_note,
                    record.source_location,
                    record.reviewed_at.isoformat(timespec="seconds") if record.reviewed_at else None,
                )
                for record in records
            ],
        )
        conn.commit()
    finally:
        conn.close()


def fetch_manual_review_records(
    review_id: str,
    path: str | Path = "data/review_runs.sqlite",
) -> list[ManualReviewRecord]:
    conn = init_db(path)
    try:
        rows = conn.execute(
            """
            SELECT record_id, review_id, field_id, field_type, extracted_value, confirmed_value,
                   review_status, review_source, reviewer_note, source_location, reviewed_at
            FROM manual_review_records
            WHERE review_id = ?
            ORDER BY field_type, source_location
            """,
            (review_id,),
        ).fetchall()
    finally:
        conn.close()
    records: list[ManualReviewRecord] = []
    for row in rows:
        reviewed_at = datetime.fromisoformat(row[10]) if row[10] else None
        records.append(
            ManualReviewRecord(
                record_id=row[0],
                review_id=row[1],
                field_id=row[2],
                field_type=row[3],
                extracted_value=row[4],
                confirmed_value=row[5],
                review_status=row[6],
                review_source=row[7],
                reviewer_note=row[8],
                source_location=row[9],
                reviewed_at=reviewed_at,
            )
        )
    return records


def _numeric_review_id(review_id: str) -> int:
    return int(str(review_id).replace("review-", ""))


def _case_from_row(row) -> CaseWorkspace:
    return CaseWorkspace(
        case_id=row[0],
        case_name=row[1],
        internal_case_no=row[2],
        client_name=row[3],
        counterparty_name=row[4],
        case_type=row[5],
        note=row[6],
        created_at=datetime.fromisoformat(row[7]),
        updated_at=datetime.fromisoformat(row[8]),
    )


def _document_from_row(row) -> CaseDocument:
    return CaseDocument(
        document_id=row[0],
        case_id=row[1],
        file_name=row[2],
        file_type=row[3],
        file_size=row[4],
        uploaded_at=datetime.fromisoformat(row[5]),
        document_role=row[6],
        note=row[7],
    )


def _summary_from_row(row) -> ReviewRunSummary:
    return ReviewRunSummary(
        review_id=row[0],
        case_id=row[1],
        case_name=row[2],
        document_id=row[3],
        file_name=row[4],
        mode_label=row[5],
        finding_count=row[6],
        high_count=row[7],
        medium_count=row[8],
        low_count=row[9],
        external_field_count=row[10],
        manual_record_count=row[11],
        config_version=row[12] or None,
        document_profile=row[13] or None,
        created_at=datetime.fromisoformat(row[14]),
    )


def _sanitize_external_fields_for_storage(fields: list[ExtractedReviewField]) -> list[ExtractedReviewField]:
    safe_labels = {
        "原告",
        "被告",
        "申请人",
        "被申请人",
        "甲方",
        "乙方",
        "原告住所地",
        "被告住所地",
        "申请人住所地",
        "被申请人住所地",
        "甲方住所地",
        "乙方住所地",
        "诉讼请求",
        "事实与理由",
        "利息起算日",
        "案件信息",
    }
    sanitized: list[ExtractedReviewField] = []
    for field in fields:
        context = field.role_or_context if field.role_or_context in safe_labels else None
        sanitized.append(field.model_copy(update={"role_or_context": context}))
    return sanitized
