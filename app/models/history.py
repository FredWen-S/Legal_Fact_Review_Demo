from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ReviewHistoryRecord(BaseModel):
    history_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    review_run_id: Optional[str] = None
    source_filename: Optional[str] = None
    document_hash: str
    mode: str
    mode_label: str
    config_version: Optional[str] = None
    document_profile: Optional[str] = None
    issue_count: int = 0
    severity_high_count: int = 0
    severity_medium_count: int = 0
    severity_low_count: int = 0
    severity_info_count: int = 0
    llm_mode: str = "not_available"
    llm_fallback_reason: Optional[str] = None
    retrieval_backend: str = "lexical"
    retrieval_status_summary: str = "not_available"
    issue_type_summary: dict[str, int] = Field(default_factory=dict)
    export_available: bool = False
    notes: Optional[str] = None


class AuditLogEntry(BaseModel):
    audit_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    event_type: str
    review_run_id: Optional[str] = None
    source_filename: Optional[str] = None
    event_summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
