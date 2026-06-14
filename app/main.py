from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from app.errors import UnsupportedFileTypeError, UserFacingError
from app.extractors.external_review_fields import build_external_review_fields
from app.manual_review import (
    REVIEW_STATUSES,
    default_manual_records,
    editor_dataframe_to_manual_records,
    manual_records_to_editor_dataframe,
    source_options_for_fields,
)
from app.parsers.docx_parser import parse_docx
from app.parsers.excel_parser import parse_base_info, parse_evidence_index
from app.parsers.ocr_pdf_parser import parse_pdf_with_ocr
from app.parsers.pdf_parser import is_scanned_pdf, parse_pdf
from app.reports.excel_report import (
    build_excel_report,
    external_fields_to_dataframe,
    findings_to_dataframe,
    manual_records_to_dataframe,
)
from app.reports.html_report import build_html_report
from app.reports.docx_report import build_docx_report
from app.reports.package_export import build_review_package_zip
from app.review_engine import review_document, review_single_document
from app.storage.sqlite_store import save_manual_review_records, save_review_run


st.set_page_config(page_title="律师文书基础信息复核助手 Demo", layout="wide")


ALLOWED_DOCUMENT_SUFFIXES = {".docx", ".pdf"}
ALLOWED_EXCEL_SUFFIXES = {".xlsx"}


def _save_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def _parse_document(path: Path, enable_ocr: bool = False):
    if path.suffix.lower() == ".docx":
        return parse_docx(path)
    if path.suffix.lower() == ".pdf":
        if enable_ocr:
            return parse_pdf_with_ocr(path)
        return parse_pdf(path)
    raise UnsupportedFileTypeError("文书仅支持 .docx 或 .pdf。请转换格式后重新上传。")


def _validate_uploaded_file(uploaded_file, label: str, suffixes: set[str]) -> list[str]:
    errors: list[str] = []
    if uploaded_file is None:
        errors.append(f"请上传{label}。")
        return errors
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in suffixes:
        allowed = "、".join(sorted(suffixes))
        errors.append(f"{label}格式不支持：{uploaded_file.name}。请上传 {allowed} 文件。")
    if uploaded_file.size == 0:
        errors.append(f"{label}为空文件。请重新导出或选择正确文件。")
    return errors


def _cleanup(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def _download_suffix() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _filter_findings(findings):
    filtered = findings
    st.subheader("结果筛选")
    col_a, col_b, col_c = st.columns([1, 1.4, 1.4])
    with col_a:
        severity = st.selectbox("风险等级", ["all", "high", "medium", "low"], format_func=lambda value: {"all": "全部", "high": "高风险", "medium": "中风险", "low": "低风险"}[value])
    with col_b:
        risk_types = sorted({finding.risk_type for finding in findings})
        selected_risk_types = st.multiselect("风险类型", risk_types, default=risk_types)
    with col_c:
        field_query = st.text_input("字段搜索", placeholder="例如：案号、金额、法定代表人")

    if severity != "all":
        filtered = [finding for finding in filtered if finding.severity == severity]
    if selected_risk_types:
        filtered = [finding for finding in filtered if finding.risk_type in selected_risk_types]
    if field_query.strip():
        query = field_query.strip()
        filtered = [finding for finding in filtered if query in finding.field_name]
    return filtered


st.title("律师文书基础信息复核助手 Demo")
st.caption("本工具仅用于辅助复核，最终判断由人工完成；默认本地运行，不上传文件到第三方服务。")
st.info("流程：上传文书 → 可选上传基础信息表和证据目录 → 点击开始复核 → 查看结果 → 导出 Excel 或 HTML 报告。")
st.warning("本工具只做基础信息和关键事实复核，不构成法律意见；未发现明显复核项也不代表文书无误。")
st.markdown(
    "如果只上传文书，系统将进入 **单文书字段抽取模式**，仅提取字段并提示人工外部复核。\n\n"
    "如果同时上传基础信息表和证据目录，系统将进入 **完整复核模式**。"
)

with st.sidebar:
    st.header("示例数据")
    st.write("可使用 `app/sample_data/` 下的示例文书、基础信息表和证据目录快速体验。")
    st.code("app/sample_data/sample_document.docx\napp/sample_data/sample_base_info.xlsx\napp/sample_data/sample_evidence_index.xlsx")
    st.warning("请勿上传超出本地运行环境授权范围的敏感材料。")

col1, col2, col3 = st.columns(3)
with col1:
    doc_file = st.file_uploader("上传文书（DOCX/PDF，必填）", type=["docx", "pdf"])
    enable_ocr = st.checkbox("启用 OCR 识别扫描版 PDF", value=False, help="仅在扫描版 PDF 或普通文本提取失败时使用。OCR 全程本地运行，但需要额外安装可选依赖。")
with col2:
    base_file = st.file_uploader("上传基础信息表（XLSX，可选）", type=["xlsx"])
with col3:
    evidence_file = st.file_uploader("上传证据目录（XLSX，可选）", type=["xlsx"])

validation_errors = []
validation_errors.extend(_validate_uploaded_file(doc_file, "文书", ALLOWED_DOCUMENT_SUFFIXES))
if base_file is not None:
    validation_errors.extend(_validate_uploaded_file(base_file, "基础信息表", ALLOWED_EXCEL_SUFFIXES))
if evidence_file is not None:
    validation_errors.extend(_validate_uploaded_file(evidence_file, "证据目录", ALLOWED_EXCEL_SUFFIXES))

run = st.button("开始复核", type="primary")

if run:
    if validation_errors:
        st.error("请先修正上传文件问题：")
        for message in validation_errors:
            st.write(f"- {message}")
        st.stop()

    temp_paths: list[Path] = []
    try:
        doc_path = _save_upload(doc_file)
        temp_paths = [doc_path]
        base_path = _save_upload(base_file) if base_file is not None else None
        evidence_path = _save_upload(evidence_file) if evidence_file is not None else None
        temp_paths.extend([path for path in [base_path, evidence_path] if path is not None])

        scanned_pdf = doc_path.suffix.lower() == ".pdf" and is_scanned_pdf(doc_path)
        if scanned_pdf and not enable_ocr:
            st.warning("该 PDF 可能是扫描件，普通文本提取结果较少。可勾选 OCR 识别后重试。")
        chunks = _parse_document(doc_path, enable_ocr=enable_ocr)
        external_fields = build_external_review_fields(chunks)
        if base_path and evidence_path:
            mode_label = "完整复核模式"
            base_info = parse_base_info(base_path)
            evidence_index = parse_evidence_index(evidence_path)
            findings = review_document(chunks, base_info, evidence_index)
        else:
            mode_label = "单文书字段抽取模式"
            findings = review_single_document(chunks)
        review_id = save_review_run(findings)
        manual_records = default_manual_records(review_id, external_fields)
        save_manual_review_records(manual_records)
        st.session_state["findings"] = findings
        st.session_state["external_fields"] = external_fields
        st.session_state["manual_records"] = manual_records
        st.session_state["review_id"] = review_id
        st.session_state["mode_label"] = mode_label
        st.session_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except UserFacingError as exc:
        st.error(str(exc))
        st.info("建议检查文件模板、文件格式和文件内容后重新上传。")
    except Exception:
        st.error("复核过程中出现未预期错误。请检查文件是否损坏，或使用示例数据验证环境是否正常。")
    finally:
        _cleanup(temp_paths)

findings = st.session_state.get("findings")
if findings is not None:
    external_fields = st.session_state.get("external_fields", [])
    manual_records = st.session_state.get("manual_records", [])
    review_id = st.session_state.get("review_id")
    mode_label = st.session_state.get("mode_label", "完整复核模式")
    if st.session_state.get("last_run_at"):
        st.caption(f"最近一次复核时间：{st.session_state['last_run_at']}")
    st.success(f"当前模式：{mode_label}")
    if mode_label == "单文书字段抽取模式" and (base_file is not None or evidence_file is not None):
        st.info("当前只上传了部分可选资料，系统按单文书字段抽取模式运行。完整复核模式需要同时上传基础信息表和证据目录。")

    high = sum(1 for item in findings if item.severity == "high")
    medium = sum(1 for item in findings if item.severity == "medium")
    low = sum(1 for item in findings if item.severity == "low")
    field_count = len({item.field_name for item in findings})
    risk_type_count = len({item.risk_type for item in findings})

    st.subheader("结果概览")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("总发现", len(findings))
    m2.metric("高风险", high)
    m3.metric("中风险", medium)
    m4.metric("低风险", low)
    m5.metric("涉及字段", field_count)
    m6.metric("风险类型", risk_type_count)

    if not findings:
        st.success("未发现明显复核项，但不代表文书无误。建议仍由人工完成最终复核。")
    else:
        filtered_findings = _filter_findings(findings)
        st.subheader("复核表格")
        if not filtered_findings:
            st.info("当前筛选条件下没有复核项。可调整风险等级、风险类型或字段搜索条件。")
        else:
            df = findings_to_dataframe(filtered_findings)
            st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("待外部复核字段清单")
    st.caption("本清单仅基于当前文书自动抽取生成，用于提示人工复核，不代表系统已完成外部核验。")
    if external_fields:
        st.dataframe(external_fields_to_dataframe(external_fields), use_container_width=True, hide_index=True)
    else:
        st.info("当前文书未抽取到可展示的外部复核字段。")

    st.subheader("人工复核工作区")
    st.caption("在这里记录人工复核状态、确认值、实际来源和备注。系统不会自动连接外部数据库，也不会修改原文书。")
    if external_fields and review_id:
        editor_df = manual_records_to_editor_dataframe(manual_records, external_fields)
        edited_df = st.data_editor(
            editor_df,
            use_container_width=True,
            hide_index=True,
            disabled=["record_id", "field_id", "字段类型", "提取值", "角色 / 上下文", "出现位置", "建议复核来源", "建议动作"],
            column_config={
                "record_id": None,
                "field_id": None,
                "复核状态": st.column_config.SelectboxColumn("复核状态", options=REVIEW_STATUSES, required=True),
                "实际复核来源": st.column_config.SelectboxColumn("实际复核来源", options=[""] + source_options_for_fields(external_fields)),
                "人工确认值": st.column_config.TextColumn("人工确认值"),
                "复核备注": st.column_config.TextColumn("复核备注"),
            },
            key=f"manual_review_editor_{review_id}",
        )
        if st.button("保存人工复核记录", type="secondary"):
            manual_records = editor_dataframe_to_manual_records(review_id, edited_df)
            save_manual_review_records(manual_records)
            st.session_state["manual_records"] = manual_records
            st.success("人工复核记录已保存到本地 SQLite。")
        st.dataframe(manual_records_to_dataframe(st.session_state.get("manual_records", manual_records)), use_container_width=True, hide_index=True)
    else:
        st.info("当前没有可处理的待外部复核字段。")

    manual_records_for_report = st.session_state.get("manual_records", manual_records)
    excel_bytes = build_excel_report(findings, external_fields, manual_records_for_report)
    html_report = build_html_report(findings, external_fields, manual_records_for_report, mode_label=mode_label)
    try:
        docx_bytes = build_docx_report(
            findings,
            external_fields,
            manual_records_for_report,
            review_id=review_id,
            mode_label=mode_label,
        )
        package_bytes = build_review_package_zip(
            findings,
            external_fields,
            manual_records_for_report,
            review_id=review_id,
            mode_label=mode_label,
        )
    except Exception:
        docx_bytes = None
        package_bytes = None
        st.error("Word 复核摘要或复核包生成失败。请先下载 Excel/HTML 报告，并检查人工复核记录是否包含异常内容。")
    suffix = _download_suffix()

    st.subheader("下载")
    dl1, dl2, dl3, dl4 = st.columns(4)
    with dl1:
        st.download_button(
            "下载字段抽取清单 Excel" if mode_label == "单文书字段抽取模式" else "下载 Excel 复核清单",
            data=excel_bytes,
            file_name=f"legal_fact_review_findings_{suffix}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with dl2:
        st.download_button(
            "下载 HTML 报告",
            data=html_report.encode("utf-8"),
            file_name=f"legal_fact_review_report_{suffix}.html",
            mime="text/html",
        )
    with dl3:
        st.download_button(
            "下载 Word 复核摘要",
            data=docx_bytes or b"",
            file_name=f"文书复核摘要_{suffix}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            disabled=docx_bytes is None,
        )
    with dl4:
        st.download_button(
            "下载完整复核包 ZIP",
            data=package_bytes or b"",
            file_name=f"review_package_{review_id or suffix}.zip",
            mime="application/zip",
            disabled=package_bytes is None,
        )
else:
    st.info("请上传文书、基础信息表和证据目录后开始复核。")
