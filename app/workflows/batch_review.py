from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.errors import UnsupportedFileTypeError, UserFacingError
from app.manual_review import default_manual_records
from app.models.schemas import ExtractedReviewField, ManualReviewRecord, ReviewFinding
from app.parsers.docx_parser import parse_docx
from app.parsers.excel_parser import parse_base_info, parse_evidence_index
from app.parsers.ocr_pdf_parser import parse_pdf_with_ocr
from app.parsers.pdf_parser import parse_pdf
from app.review_engine import review_document_result, review_single_document_result
from app.storage.sqlite_store import save_case_document, save_manual_review_records, save_review_run


@dataclass(frozen=True)
class BatchInputFile:
    path: Path
    file_name: str
    file_size: int
    document_role: str | None = None
    note: str | None = None


@dataclass
class BatchReviewResult:
    file_name: str
    mode_label: str
    review_id: str | None
    finding_count: int
    high_count: int
    medium_count: int
    low_count: int
    external_field_count: int
    status: str
    error: str | None = None
    findings: list[ReviewFinding] | None = None
    external_fields: list[ExtractedReviewField] | None = None
    manual_records: list[ManualReviewRecord] | None = None


def run_batch_review(
    files: list[BatchInputFile],
    base_info_path: str | Path | None = None,
    evidence_index_path: str | Path | None = None,
    case_id: str | None = None,
    enable_ocr: bool = False,
    db_path: str | Path = "data/review_runs.sqlite",
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
) -> list[BatchReviewResult]:
    config = config or load_review_config()
    base_info = parse_base_info(base_info_path) if base_info_path and evidence_index_path else None
    evidence_index = parse_evidence_index(evidence_index_path) if base_info_path and evidence_index_path else None
    mode_label = "完整复核模式" if base_info is not None and evidence_index is not None else "单文书字段抽取模式"

    results: list[BatchReviewResult] = []
    for item in files:
        try:
            chunks = _parse_document(item.path, enable_ocr=enable_ocr)
            if base_info is not None and evidence_index is not None:
                review_result = review_document_result(
                    chunks,
                    base_info,
                    evidence_index,
                    config=config,
                    document_profile=document_profile,
                )
            else:
                review_result = review_single_document_result(
                    chunks,
                    config=config,
                    document_profile=document_profile,
                )
            findings = review_result.findings
            external_fields = review_result.external_fields

            document_id = None
            if case_id:
                document = save_case_document(
                    case_id=case_id,
                    file_name=item.file_name,
                    file_type=item.path.suffix.lower().lstrip("."),
                    file_size=item.file_size,
                    document_role=item.document_role,
                    note=item.note,
                    path=db_path,
                )
                document_id = document.document_id

            review_id = save_review_run(
                findings,
                path=db_path,
                external_fields=external_fields,
                case_id=case_id,
                document_id=document_id,
                file_name=item.file_name,
                mode_label=mode_label,
                config_version=config.config_version,
                document_profile=document_profile,
                structured_extraction=review_result.structured_extraction,
                knowledge_context=review_result.knowledge_context,
            )
            manual_records = default_manual_records(review_id, external_fields)
            save_manual_review_records(manual_records, db_path)

            high = sum(1 for finding in findings if finding.severity == "high")
            medium = sum(1 for finding in findings if finding.severity == "medium")
            low = sum(1 for finding in findings if finding.severity == "low")
            results.append(
                BatchReviewResult(
                    file_name=item.file_name,
                    mode_label=mode_label,
                    review_id=review_id,
                    finding_count=len(findings),
                    high_count=high,
                    medium_count=medium,
                    low_count=low,
                    external_field_count=len(external_fields),
                    status="成功",
                    findings=findings,
                    external_fields=external_fields,
                    manual_records=manual_records,
                )
            )
        except (UserFacingError, UnsupportedFileTypeError, Exception) as exc:
            results.append(
                BatchReviewResult(
                    file_name=item.file_name,
                    mode_label=mode_label,
                    review_id=None,
                    finding_count=0,
                    high_count=0,
                    medium_count=0,
                    low_count=0,
                    external_field_count=0,
                    status="失败",
                    error=str(exc) or exc.__class__.__name__,
                )
            )
    return results


def _parse_document(path: Path, enable_ocr: bool = False):
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        if enable_ocr:
            return parse_pdf_with_ocr(path)
        return parse_pdf(path)
    raise UnsupportedFileTypeError("文书仅支持 .docx 或 .pdf。请转换格式后重新上传。")
