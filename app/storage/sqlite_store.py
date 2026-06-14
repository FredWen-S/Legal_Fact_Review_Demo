from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.models.schemas import ManualReviewRecord, ReviewFinding


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
    conn.commit()
    return conn


def save_review_run(findings: list[ReviewFinding], path: str | Path = "data/review_runs.sqlite") -> str:
    conn = init_db(path)
    try:
        created_at = datetime.now().isoformat(timespec="seconds")
        cursor = conn.execute(
            "INSERT INTO review_runs (created_at, finding_count, findings_json) VALUES (?, ?, ?)",
            (
                created_at,
                len(findings),
                json.dumps([finding.model_dump() for finding in findings], ensure_ascii=False),
            ),
        )
        conn.commit()
        return f"review-{cursor.lastrowid}"
    finally:
        conn.close()


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
