from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.config.review_config import ReviewRulesConfig, load_review_config
from app.errors import UnsupportedFileTypeError, UserFacingError
from app.models.schemas import (
    BaseInfoItem,
    EvidenceItem,
    ReviewResult,
    TextChunk,
)
from app.parsers.docx_parser import parse_docx
from app.parsers.excel_parser import parse_base_info, parse_evidence_index
from app.parsers.ocr_pdf_parser import parse_pdf_with_ocr
from app.parsers.pdf_parser import is_scanned_pdf, parse_pdf
from app.review_engine import review_document_result, review_single_document_result
from app.storage.review_history import build_review_history_metadata, stable_document_hash


SingleReviewMode = Literal["single_document", "full_review"]

SINGLE_DOCUMENT_MODE_LABEL = "单文书字段抽取模式"
FULL_REVIEW_MODE_LABEL = "完整复核模式"
PARTIAL_FULL_REVIEW_WARNING = "完整复核需要同时上传基础信息表和证据目录；当前将按单文书模式运行。"


@dataclass
class SingleReviewWorkflowResult:
    mode: SingleReviewMode
    mode_label: str
    review_result: ReviewResult | None = None
    export_context: dict[str, Any] = field(default_factory=dict)
    history_metadata: dict[str, Any] = field(default_factory=dict)
    audit_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.review_result is not None


def run_single_review_workflow(
    document_path: str | Path,
    base_info_path: str | Path | None = None,
    evidence_index_path: str | Path | None = None,
    enable_ocr: bool = False,
    config: ReviewRulesConfig | None = None,
    document_profile: str | None = None,
    source_filename: str | None = None,
) -> SingleReviewWorkflowResult:
    warnings: list[str] = []
    errors: list[str] = []
    doc_path = Path(document_path)
    config = config or load_review_config()
    display_filename = source_filename or doc_path.name
    document_hash = stable_document_hash(doc_path, display_filename)

    if not doc_path.exists() or not doc_path.is_file():
        return _error_result(
            "single_document",
            SINGLE_DOCUMENT_MODE_LABEL,
            f"主文书路径不存在：{doc_path}",
            warnings,
            config,
            document_profile,
            display_filename,
            document_hash,
        )

    base_path = Path(base_info_path) if base_info_path is not None else None
    evidence_path = Path(evidence_index_path) if evidence_index_path is not None else None
    mode: SingleReviewMode = "single_document"
    mode_label = SINGLE_DOCUMENT_MODE_LABEL
    if base_path is not None and evidence_path is not None:
        mode = "full_review"
        mode_label = FULL_REVIEW_MODE_LABEL
    elif base_path is not None or evidence_path is not None:
        warnings.append(PARTIAL_FULL_REVIEW_WARNING)

    if doc_path.suffix.lower() == ".pdf" and not enable_ocr:
        try:
            if is_scanned_pdf(doc_path):
                warnings.append("该 PDF 可能是扫描件，普通文本提取结果较少。可勾选 OCR 识别后重试。")
        except Exception:
            warnings.append("PDF 扫描件检测未完成，系统将继续尝试普通文本解析。")

    try:
        chunks = _parse_document(doc_path, enable_ocr=enable_ocr)
    except UserFacingError as exc:
        return _error_result(mode, mode_label, str(exc), warnings, config, document_profile, display_filename, document_hash)
    except Exception:
        return _error_result(
            mode,
            mode_label,
            "文书解析失败。请检查文件是否损坏，或使用示例数据验证环境是否正常。",
            warnings,
            config,
            document_profile,
            display_filename,
            document_hash,
        )

    base_info: list[BaseInfoItem] = []
    evidence_index: list[EvidenceItem] = []
    if mode == "full_review":
        try:
            base_info = parse_base_info(base_path)  # type: ignore[arg-type]
            evidence_index = parse_evidence_index(evidence_path)  # type: ignore[arg-type]
        except UserFacingError as exc:
            return _error_result(mode, mode_label, str(exc), warnings, config, document_profile, display_filename, document_hash)
        except Exception:
            return _error_result(
                mode,
                mode_label,
                "基础信息表或证据目录解析失败。请确认上传的是未损坏且符合模板的 .xlsx 文件。",
                warnings,
                config,
                document_profile,
                display_filename,
                document_hash,
            )

    try:
        if mode == "full_review":
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
    except UserFacingError as exc:
        return _error_result(mode, mode_label, str(exc), warnings, config, document_profile, display_filename, document_hash)
    except Exception:
        return _error_result(
            mode,
            mode_label,
            "复核引擎执行失败。请检查输入文件内容，或使用示例数据验证环境是否正常。",
            warnings,
            config,
            document_profile,
            display_filename,
            document_hash,
        )
    history_record = build_review_history_metadata(
        review_result,
        source_filename=display_filename,
        document_hash=document_hash,
        mode=mode,
        mode_label=mode_label,
        config_version=config.config_version,
        document_profile=document_profile,
        export_available=True,
        notes="single_review_workflow",
    )

    return SingleReviewWorkflowResult(
        mode=mode,
        mode_label=mode_label,
        review_result=review_result,
        export_context=_build_export_context(
            review_result,
            mode_label,
            config,
            document_profile,
            display_filename,
        ),
        history_metadata=history_record.model_dump(mode="json", exclude={"history_id"}),
        audit_metadata=_build_audit_metadata(mode, mode_label, config, document_profile, display_filename, document_hash),
        warnings=warnings,
        errors=errors,
    )


def _parse_document(path: Path, enable_ocr: bool = False) -> list[TextChunk]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        if enable_ocr:
            return parse_pdf_with_ocr(path)
        return parse_pdf(path)
    raise UnsupportedFileTypeError("文书仅支持 .docx 或 .pdf。请转换格式后重新上传。")


def _build_export_context(
    review_result: ReviewResult | None,
    mode_label: str,
    config: ReviewRulesConfig,
    document_profile: str | None,
    source_filename: str,
) -> dict[str, Any]:
    return {
        "mode_label": mode_label,
        "config_version": config.config_version,
        "config_updated_at": config.updated_at,
        "document_profile": document_profile,
        "source_filename": source_filename,
        "structured_extraction": review_result.structured_extraction if review_result else None,
        "knowledge_context": review_result.knowledge_context if review_result else None,
    }


def _error_result(
    mode: SingleReviewMode,
    mode_label: str,
    message: str,
    warnings: list[str],
    config: ReviewRulesConfig,
    document_profile: str | None,
    source_filename: str,
    document_hash: str,
) -> SingleReviewWorkflowResult:
    return SingleReviewWorkflowResult(
        mode=mode,
        mode_label=mode_label,
        review_result=None,
        export_context=_build_export_context(None, mode_label, config, document_profile, source_filename),
        audit_metadata={
            **_build_audit_metadata(mode, mode_label, config, document_profile, source_filename, document_hash),
            "error": message,
        },
        warnings=warnings,
        errors=[message],
    )


def _build_audit_metadata(
    mode: SingleReviewMode,
    mode_label: str,
    config: ReviewRulesConfig,
    document_profile: str | None,
    source_filename: str,
    document_hash: str,
) -> dict[str, Any]:
    return {
        "source_filename": source_filename,
        "document_hash": document_hash,
        "mode": mode,
        "mode_label": mode_label,
        "config_version": config.config_version,
        "document_profile": document_profile,
    }
