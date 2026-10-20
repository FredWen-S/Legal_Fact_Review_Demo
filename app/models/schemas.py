from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

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
    "SPELLING_VARIATION",
    "CLAUSE_NUMBERING_ERROR",
    "CLIENT_PROFILE_MISMATCH",
    "MISSING_STANDARD_CLAUSE",
    "TEMPLATE_FIELD_MISMATCH",
    "STATUTE_REPEALED",
    "STATUTE_ARTICLE_OUT_OF_RANGE",
    "STATUTE_UNVERIFIED",
]

Severity = Literal["low", "medium", "high"]
EntityType = Literal[
    "party",
    "company_name",
    "credit_code",
    "legal_representative",
    "registered_address",
    "date",
    "amount",
    "contract_id",
    "statute_reference",
]
ExplanationMode = Literal["mock", "llm"]
KnowledgeType = Literal["client", "clause", "template"]
RetrievalStatus = Literal["matched", "no_match", "low_confidence_match"]

FORBIDDEN_REVIEW_TERMS = {
    "system confirmed error",
    "confirmed legal conclusion",
    "法律上必然",
    "系统确认错误",
    "自动核验通过",
}


class ReviewFinding(BaseModel):
    risk_id: str
    risk_type: RiskType
    severity: Severity
    field_name: str
    document_value: Optional[str]
    reference_value: Optional[str]
    source_location: str
    reference_source: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    reason: str
    suggested_action: str
    risk_explanation: Optional[str] = None
    explanation_source: Optional[ExplanationMode] = None

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"low", "medium", "high"}:
            raise ValueError("severity must be low, medium, or high")
        return normalized

    @field_validator("source_location")
    @classmethod
    def source_location_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source_location is required")
        return value

    @field_validator("suggested_action")
    @classmethod
    def must_be_review_suggestion(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("suggested_action is required")
        lower = text.lower()
        if any(term in lower for term in FORBIDDEN_REVIEW_TERMS):
            raise ValueError("suggested_action must not claim a confirmed legal conclusion")
        if "人工复核" not in text and "manual review" not in lower:
            raise ValueError("suggested_action must clearly recommend manual review")
        return text

    @property
    def issue_type(self) -> str:
        return self.risk_type

    @property
    def original_text(self) -> Optional[str]:
        return self.document_value

    @property
    def suggested_text(self) -> str:
        return self.suggested_action

    @property
    def evidence_source(self) -> str:
        return self.source_location

    @property
    def explanation(self) -> str:
        return self.reason

    @property
    def severity_label(self) -> str:
        return self.severity.upper()

    def to_issue_record(self) -> dict[str, Any]:
        return {
            "severity": self.severity_label,
            "issue_type": self.issue_type,
            "original_text": self.original_text,
            "suggested_text": self.suggested_text,
            "evidence_source": self.evidence_source,
            "explanation": self.explanation,
            "field_name": self.field_name,
            "reference_value": self.reference_value,
            "reference_source": self.reference_source,
            "confidence": self.confidence,
            "risk_explanation": self.risk_explanation,
            "explanation_source": self.explanation_source,
        }


class ExtractedReviewField(BaseModel):
    field_id: str
    field_type: str
    value: str
    role_or_context: Optional[str] = None
    source_location: str
    confidence: float = Field(ge=0, le=1)
    suggested_review_sources: list[str]
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
        text = value.strip()
        if not text:
            raise ValueError("suggested_action is required")
        lower = text.lower()
        if any(term in lower for term in FORBIDDEN_REVIEW_TERMS):
            raise ValueError("suggested_action must not claim a confirmed legal conclusion")
        if "人工复核" not in text and "manual review" not in lower:
            raise ValueError("suggested_action must clearly recommend manual review")
        return text


class ManualReviewRecord(BaseModel):
    record_id: str
    review_id: str
    field_id: str
    field_type: str
    extracted_value: str
    confirmed_value: Optional[str] = None
    review_status: str = "未复核"
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
        lower = value.lower()
        if any(term in lower for term in FORBIDDEN_REVIEW_TERMS):
            raise ValueError("manual review text must not claim a confirmed legal conclusion")
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


class StructuredEntity(BaseModel):
    entity_type: EntityType
    value: str
    normalized_value: Optional[str] = None
    role: Optional[str] = None
    source_location: str
    confidence: float = Field(default=0.8, ge=0, le=1)
    context: Optional[str] = None

    @field_validator("source_location")
    @classmethod
    def structured_source_location_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source_location is required")
        return value


class StructuredExtractionResult(BaseModel):
    mode: Literal["mock", "llm"]
    model_name: Optional[str] = None
    prompt_version: str = "legal-review-structured-extraction-v1"
    entities: list[StructuredEntity] = Field(default_factory=list)
    raw_response: Optional[str] = None
    fallback_reason: Optional[str] = None

    def by_type(self, entity_type: EntityType) -> list[StructuredEntity]:
        return [entity for entity in self.entities if entity.entity_type == entity_type]

    def values(self, entity_type: EntityType) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for entity in self.by_type(entity_type):
            value = entity.normalized_value or entity.value
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered


class RiskExplanationResult(BaseModel):
    mode: ExplanationMode
    model_name: Optional[str] = None
    prompt_version: str = "legal-review-risk-explanation-v1"
    explained_count: int = 0
    llm_explained_count: int = 0
    fallback_reason: Optional[str] = None


class KnowledgeMatch(BaseModel):
    kb_type: KnowledgeType
    doc_id: str
    title: str
    score: float
    path: str
    snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    match_status: RetrievalStatus = "matched"
    match_reason: str = ""
    min_score: float = 0.0


class KnowledgeRetrievalStatus(BaseModel):
    kb_type: KnowledgeType
    status: RetrievalStatus
    min_score: float = 0.0
    best_score: Optional[float] = None
    best_doc_id: Optional[str] = None
    match_reason: str


class KnowledgeContext(BaseModel):
    client_profile: Optional[KnowledgeMatch] = None
    clauses: list[KnowledgeMatch] = Field(default_factory=list)
    templates: list[KnowledgeMatch] = Field(default_factory=list)
    retrieval_statuses: list[KnowledgeRetrievalStatus] = Field(default_factory=list)

    def status_for(self, kb_type: KnowledgeType) -> KnowledgeRetrievalStatus | None:
        for status in self.retrieval_statuses:
            if status.kb_type == kb_type:
                return status
        return None


class ReviewResult(BaseModel):
    findings: list[ReviewFinding] = Field(default_factory=list)
    external_fields: list[ExtractedReviewField] = Field(default_factory=list)
    structured_extraction: Optional[StructuredExtractionResult] = None
    knowledge_context: KnowledgeContext = Field(default_factory=KnowledgeContext)
    risk_explanation: Optional[RiskExplanationResult] = None

    def severity_counts(self) -> dict[str, int]:
        return {
            "HIGH": sum(1 for item in self.findings if item.severity == "high"),
            "MEDIUM": sum(1 for item in self.findings if item.severity == "medium"),
            "LOW": sum(1 for item in self.findings if item.severity == "low"),
        }


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
    findings: list[ReviewFinding] = Field(default_factory=list)
    external_fields: list[ExtractedReviewField] = Field(default_factory=list)
    manual_records: list[ManualReviewRecord] = Field(default_factory=list)
    structured_extraction: Optional[StructuredExtractionResult] = None
    knowledge_context: Optional[KnowledgeContext] = None


class FieldDifference(BaseModel):
    field_type: str
    left_value: str
    right_value: str
    documents: str
    suggested_action: str

    @field_validator("suggested_action")
    @classmethod
    def difference_action_must_be_review_suggestion(cls, value: str) -> str:
        text = value.strip()
        if "人工复核" not in text and "manual review" not in text.lower():
            raise ValueError("difference suggested_action must clearly recommend manual review")
        return text


class RuleConfigHistory(BaseModel):
    config_history_id: int
    config_version: str
    saved_at: datetime
    change_note: Optional[str] = None
    backup_path: Optional[str] = None
    active_config_path: str
