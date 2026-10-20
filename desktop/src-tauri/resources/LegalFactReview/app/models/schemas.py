from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


RiskType = Literal[
    "MISSING_FIELD",
    "INTERNAL_CONFLICT",
    "SOURCE_MISMATCH",
    "FORMAT_ERROR",
    "POSSIBLY_OUTDATED",
    "PLACEHOLDER_REMAINING",
    "EVIDENCE_REFERENCE_MISSING",
    "AMOUNT_INCONSISTENCY",
    "DATE_LOGIC_WARNING",
]


class ReviewFinding(BaseModel):
    risk_id: str
    risk_type: RiskType
    severity: Literal["low", "medium", "high"]
    field_name: str
    document_value: Optional[str]
    reference_value: Optional[str]
    source_location: str
    reference_source: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    reason: str
    suggested_action: str

    @field_validator("source_location")
    @classmethod
    def source_location_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source_location is required")
        return value

    @field_validator("suggested_action")
    @classmethod
    def must_be_review_suggestion(cls, value: str) -> str:
        forbidden = ["系统已确认错误", "确认错误", "必然错误", "法律上必然", "无效"]
        if any(term in value for term in forbidden):
            raise ValueError("suggested_action must not claim confirmed error or legal conclusion")
        if "建议人工复核" not in value:
            raise ValueError("suggested_action must be phrased as a manual review suggestion")
        return value


class ExtractedReviewField(BaseModel):
    field_id: str
    field_type: str
    value: str
    role_or_context: Optional[str] = None
    source_location: str
    confidence: float = Field(ge=0, le=1)
    suggested_review_sources: List[str]
    suggested_action: str

    @field_validator("source_location")
    @classmethod
    def extracted_source_location_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source_location is required")
        return value

    @field_validator("suggested_action")
    @classmethod
    def extracted_action_must_be_review_suggestion(cls, value: str) -> str:
        forbidden = ["系统已确认错误", "确认错误", "必然错误", "法律上必然", "无效"]
        if any(term in value for term in forbidden):
            raise ValueError("suggested_action must not claim a confirmed error or legal conclusion")
        if "建议人工复核" not in value:
            raise ValueError("suggested_action must be phrased as a manual review suggestion")
        return value



class ManualReviewRecord(BaseModel):
    record_id: str
    review_id: str
    field_id: str
    field_type: str
    extracted_value: str
    confirmed_value: Optional[str] = None
    review_status: Literal["未复核", "已确认", "需修改", "已忽略"] = "未复核"
    review_source: Optional[str] = None
    reviewer_note: Optional[str] = None
    source_location: str
    reviewed_at: Optional[datetime] = None

    @field_validator("source_location")
    @classmethod
    def manual_source_location_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source_location is required")
        return value

    @field_validator("confirmed_value", "reviewer_note")
    @classmethod
    def manual_text_must_not_claim_legal_conclusion(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        forbidden = ["系统已确认错误", "法律上必然", "必然无效"]
        if any(term in value for term in forbidden):
            raise ValueError("manual review text must not claim a system-confirmed error or legal conclusion")
        return value


class TextChunk(BaseModel):
    text: str
    location: str


class ExtractedItem(BaseModel):
    field_name: str
    value: str
    source_location: str
    confidence: float = Field(default=0.8, ge=0, le=1)
    context: Optional[str] = None


class BaseInfoItem(BaseModel):
    field_name: str
    standard_value: str
    updated_at: Optional[str] = None
    remark: Optional[str] = None


class EvidenceItem(BaseModel):
    evidence_no: str
    evidence_name: str
    location: Optional[str] = None
    remark: Optional[str] = None


class CaseWorkspace(BaseModel):
    case_id: str
    case_name: str
    internal_case_no: Optional[str] = None
    client_name: Optional[str] = None
    counterparty_name: Optional[str] = None
    case_type: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CaseDocument(BaseModel):
    document_id: str
    case_id: str
    file_name: str
    file_type: str
    file_size: int
    uploaded_at: datetime
    document_role: Optional[str] = None
    note: Optional[str] = None


class ReviewRunSummary(BaseModel):
    review_id: str
    case_id: Optional[str] = None
    case_name: Optional[str] = None
    document_id: Optional[str] = None
    file_name: Optional[str] = None
    mode_label: str = "完整复核模式"
    finding_count: int
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    external_field_count: int = 0
    manual_record_count: int = 0
    config_version: Optional[str] = None
    document_profile: Optional[str] = None
    created_at: datetime


class ReviewRunDetail(ReviewRunSummary):
    findings: List[ReviewFinding] = Field(default_factory=list)
    external_fields: List[ExtractedReviewField] = Field(default_factory=list)
    manual_records: List[ManualReviewRecord] = Field(default_factory=list)


class FieldDifference(BaseModel):
    field_type: str
    left_value: str
    right_value: str
    documents: str
    suggested_action: str

    @field_validator("suggested_action")
    @classmethod
    def difference_action_must_be_review_suggestion(cls, value: str) -> str:
        if "建议人工复核" not in value:
            raise ValueError("difference suggested_action must be phrased as a manual review suggestion")
        return value


class RuleConfigHistory(BaseModel):
    config_history_id: int
    config_version: str
    saved_at: datetime
    change_note: Optional[str] = None
    backup_path: Optional[str] = None
    active_config_path: str
