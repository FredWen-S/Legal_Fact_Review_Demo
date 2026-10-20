from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from app.errors import UnsupportedFileTypeError, UserFacingError
from app.config.review_config import DEFAULT_CONFIG_PATH, VALID_RISK_TYPES, export_config, load_review_config, load_review_config_with_status, validate_config_data
from app.config.rule_config_service import import_rules_with_history, restore_default_rules_with_history
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
from app.reports.docx_annotation import annotated_docx_filename, build_annotated_docx
from app.reports.case_package import build_case_review_package_zip
from app.reports.docx_report import build_docx_report
from app.reports.excel_report import build_excel_report, external_fields_to_dataframe, findings_to_dataframe, manual_records_to_dataframe
from app.reports.html_report import build_html_report
from app.reports.package_export import build_review_package_zip
from app.review_engine import review_document, review_single_document
from app.storage.sqlite_store import (
    create_case_workspace,
    delete_case_workspace,
    delete_review_run,
    fetch_manual_review_records,
    get_case_workspace,
    get_review_run_detail,
    list_case_documents,
    list_case_workspaces,
    list_review_runs,
    save_manual_review_records,
    save_review_run,
    list_rule_config_history,
)
from app.workflows.batch_review import BatchInputFile, run_batch_review
from app.workflows.case_differences import build_case_field_differences


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


def _selected_case_id() -> str | None:
    return st.session_state.get("selected_case_id") or None


def _case_options() -> dict[str, str]:
    cases = list_case_workspaces()
    return {f"{case.case_name} ({case.internal_case_no or case.case_id})": case.case_id for case in cases}


def _render_case_selector() -> None:
    st.sidebar.header("案件工作区")
    options = {"临时复核模式": ""}
    options.update(_case_options())
    current = st.session_state.get("selected_case_id", "")
    labels = list(options.keys())
    default_index = next((index for index, label in enumerate(labels) if options[label] == current), 0)
    selected_label = st.sidebar.selectbox("当前案件", labels, index=default_index)
    st.session_state["selected_case_id"] = options[selected_label]
    if options[selected_label]:
        case = get_case_workspace(options[selected_label])
        if case:
            st.sidebar.caption(f"客户：{case.client_name or '未填写'}")
            st.sidebar.caption(f"对方：{case.counterparty_name or '未填写'}")
    else:
        st.sidebar.caption("未选择案件时，复核记录将保存为临时记录。")


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


def _store_current_review(review_id, findings, external_fields, manual_records, mode_label, source_docx_bytes=None, source_filename=None) -> None:
    st.session_state["findings"] = findings
    st.session_state["external_fields"] = external_fields
    st.session_state["manual_records"] = manual_records
    st.session_state["review_id"] = review_id
    st.session_state["mode_label"] = mode_label
    st.session_state["source_docx_bytes"] = source_docx_bytes
    st.session_state["source_filename"] = source_filename
    config = load_review_config()
    st.session_state["config_version"] = config.config_version
    st.session_state["config_updated_at"] = config.updated_at
    st.session_state["document_profile"] = st.session_state.get("document_profile", "general")
    st.session_state["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _render_review_result() -> None:
    findings = st.session_state.get("findings")
    if findings is None:
        st.info("请上传文书、基础信息表和证据目录后开始复核。")
        return

    external_fields = st.session_state.get("external_fields", [])
    manual_records = st.session_state.get("manual_records", [])
    review_id = st.session_state.get("review_id")
    mode_label = st.session_state.get("mode_label", "完整复核模式")
    if st.session_state.get("last_run_at"):
        st.caption(f"最近一次复核时间：{st.session_state['last_run_at']}")
    st.success(f"当前模式：{mode_label}")

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
        if filtered_findings:
            st.dataframe(findings_to_dataframe(filtered_findings), use_container_width=True, hide_index=True)
        else:
            st.info("当前筛选条件下没有复核项。")

    st.subheader("待外部复核字段清单")
    st.caption("本清单仅基于当前文书自动抽取生成，用于提示人工复核，外部来源仍需人工核对。")
    if external_fields:
        st.dataframe(external_fields_to_dataframe(external_fields), use_container_width=True, hide_index=True)
    else:
        st.info("当前文书未抽取到可展示的外部复核字段。")

    _render_manual_review_editor(review_id, external_fields, manual_records)
    _render_downloads(
        findings,
        external_fields,
        st.session_state.get("manual_records", manual_records),
        review_id,
        mode_label,
        st.session_state.get("source_docx_bytes"),
        st.session_state.get("source_filename"),
        st.session_state.get("config_version"),
        st.session_state.get("document_profile"),
        st.session_state.get("config_updated_at"),
    )


def _render_manual_review_editor(review_id, external_fields, manual_records) -> None:
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
        if st.button("保存人工复核记录", type="secondary", key=f"save_manual_{review_id}"):
            manual_records = editor_dataframe_to_manual_records(review_id, edited_df)
            save_manual_review_records(manual_records)
            st.session_state["manual_records"] = manual_records
            st.success("人工复核记录已保存到本地 SQLite。")
        st.dataframe(manual_records_to_dataframe(st.session_state.get("manual_records", manual_records)), use_container_width=True, hide_index=True)
    else:
        st.info("当前没有可处理的待外部复核字段。")


def _render_downloads(findings, external_fields, manual_records, review_id, mode_label, source_docx_bytes=None, source_filename=None, config_version=None, document_profile=None, config_updated_at=None) -> None:
    excel_bytes = build_excel_report(findings, external_fields, manual_records, config_version=config_version, document_profile=document_profile, config_updated_at=config_updated_at)
    html_report = build_html_report(findings, external_fields, manual_records, mode_label=mode_label, config_version=config_version, document_profile=document_profile, config_updated_at=config_updated_at)
    docx_bytes = build_docx_report(findings, external_fields, manual_records, review_id=review_id, mode_label=mode_label, config_version=config_version, document_profile=document_profile, config_updated_at=config_updated_at)
    package_bytes = build_review_package_zip(
        findings,
        external_fields,
        manual_records,
        review_id=review_id,
        mode_label=mode_label,
        source_docx=source_docx_bytes,
        source_filename=source_filename,
        config_version=config_version,
        document_profile=document_profile,
        config_updated_at=config_updated_at,
    )
    annotated_bytes = None
    if source_docx_bytes is not None and source_filename:
        annotated_bytes = build_annotated_docx(source_docx_bytes, findings, external_fields, manual_records)
    suffix = _download_suffix()

    st.subheader("下载")
    dl1, dl2, dl3, dl4, dl5 = st.columns(5)
    with dl1:
        st.download_button("下载 Excel 复核清单", data=excel_bytes, file_name=f"legal_fact_review_findings_{suffix}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with dl2:
        st.download_button("下载 HTML 报告", data=html_report.encode("utf-8"), file_name=f"legal_fact_review_report_{suffix}.html", mime="text/html")
    with dl3:
        st.download_button("下载 Word 复核摘要", data=docx_bytes, file_name=f"文书复核摘要_{suffix}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with dl4:
        st.download_button("下载完整复核包 ZIP", data=package_bytes, file_name=f"review_package_{review_id or suffix}.zip", mime="application/zip")
    with dl5:
        annotation_help = (
            "仅支持当前会话上传的 DOCX。PDF 不支持原文提示版，可下载 Word 复核摘要。历史记录没有保存原文书，无法生成提示版。"
            if annotated_bytes is None
            else "生成新的 DOCX 副本，不覆盖原文。提示内容仅用于人工复核。"
        )
        st.download_button(
            "下载 Word 复核提示版",
            data=annotated_bytes or b"",
            file_name=annotated_docx_filename(source_filename or "文书.docx"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            disabled=annotated_bytes is None,
            help=annotation_help,
        )


def render_single_review_page() -> None:
    st.header("单次复核")
    st.info("如果只上传文书，系统进入单文书字段抽取模式；如果同时上传基础信息表和证据目录，系统进入完整复核模式。")
    selected_case_id = _selected_case_id()
    config = load_review_config()
    profile_options = {f"{profile.display_name} ({key})": key for key, profile in config.document_profiles.items()}
    selected_profile_label = st.selectbox("文书类型模板", list(profile_options), index=0)
    document_profile = profile_options[selected_profile_label]
    st.session_state["document_profile"] = document_profile
    if selected_case_id:
        st.caption(f"当前复核将归入案件：{get_case_workspace(selected_case_id).case_name}")
    else:
        st.caption("当前为临时复核模式。")

    col1, col2, col3 = st.columns(3)
    with col1:
        doc_file = st.file_uploader("上传文书（DOCX/PDF，必填）", type=["docx", "pdf"])
        enable_ocr = st.checkbox("启用 OCR 识别扫描版 PDF", value=False)
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

    if st.button("开始复核", type="primary"):
        if validation_errors:
            st.error("请先修正上传文件问题：")
            for message in validation_errors:
                st.write(f"- {message}")
            st.stop()

        temp_paths: list[Path] = []
        try:
            source_docx_bytes = doc_file.getvalue() if Path(doc_file.name).suffix.lower() == ".docx" else None
            doc_path = _save_upload(doc_file)
            temp_paths = [doc_path]
            base_path = _save_upload(base_file) if base_file is not None else None
            evidence_path = _save_upload(evidence_file) if evidence_file is not None else None
            temp_paths.extend([path for path in [base_path, evidence_path] if path is not None])

            if doc_path.suffix.lower() == ".pdf" and is_scanned_pdf(doc_path) and not enable_ocr:
                st.warning("该 PDF 可能是扫描件，普通文本提取结果较少。可勾选 OCR 识别后重试。")
            chunks = _parse_document(doc_path, enable_ocr=enable_ocr)
            external_fields = build_external_review_fields(chunks, config=config)
            if base_path and evidence_path:
                mode_label = "完整复核模式"
                findings = review_document(chunks, parse_base_info(base_path), parse_evidence_index(evidence_path), config=config, document_profile=document_profile)
            else:
                mode_label = "单文书字段抽取模式"
                findings = review_single_document(chunks, config=config)
            review_id = save_review_run(findings, external_fields=external_fields, case_id=selected_case_id, file_name=doc_file.name, mode_label=mode_label, config_version=config.config_version, document_profile=document_profile)
            manual_records = default_manual_records(review_id, external_fields)
            save_manual_review_records(manual_records)
            _store_current_review(review_id, findings, external_fields, manual_records, mode_label, source_docx_bytes, doc_file.name if source_docx_bytes else None)
        except UserFacingError as exc:
            st.error(str(exc))
        except Exception:
            st.error("复核过程中出现未预期错误。请检查文件是否损坏，或使用示例数据验证环境是否正常。")
        finally:
            _cleanup(temp_paths)

    _render_review_result()


def render_case_workspace_page() -> None:
    st.header("案件工作区")
    with st.expander("新建案件", expanded=False):
        with st.form("create_case_form"):
            case_name = st.text_input("案件名称")
            internal_case_no = st.text_input("案件编号（内部自定义）")
            client_name = st.text_input("客户名称")
            counterparty_name = st.text_input("对方主体")
            case_type = st.text_input("案件类型")
            note = st.text_area("备注")
            submitted = st.form_submit_button("创建案件")
        if submitted:
            if not case_name.strip():
                st.error("请填写案件名称。")
            else:
                case = create_case_workspace(case_name.strip(), internal_case_no.strip() or None, client_name.strip() or None, counterparty_name.strip() or None, case_type.strip() or None, note.strip() or None)
                st.session_state["selected_case_id"] = case.case_id
                st.success("案件已创建。")
                st.rerun()

    cases = list_case_workspaces()
    if not cases:
        st.info("暂无案件工作区。可以先创建案件，或继续使用临时复核模式。")
        return
    rows = [case.model_dump() for case in cases]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    selected_case_id = _selected_case_id()
    if selected_case_id:
        case = get_case_workspace(selected_case_id)
        st.subheader("当前案件")
        st.json(case.model_dump(mode="json") if case else {})
        documents = list_case_documents(selected_case_id)
        st.write("案件文书元数据")
        st.dataframe(pd.DataFrame([doc.model_dump(mode="json") for doc in documents]), use_container_width=True, hide_index=True)

        differences = build_case_field_differences(selected_case_id)
        st.subheader("案件内字段差异提示")
        st.caption("仅表示不同文书之间字段不一致，需人工判断是否属于正常版本差异。")
        if differences:
            st.dataframe(pd.DataFrame([item.model_dump() for item in differences]), use_container_width=True, hide_index=True)
        else:
            st.info("当前案件暂无可展示的字段差异提示。")

        package_bytes = build_case_review_package_zip(selected_case_id)
        st.download_button("导出案件级复核包", data=package_bytes, file_name=f"case_review_package_{selected_case_id}.zip", mime="application/zip")

        st.subheader("删除案件")
        confirm = st.checkbox("我确认删除当前案件及其关联历史记录", key="confirm_delete_case")
        if st.button("删除当前案件", disabled=not confirm):
            delete_case_workspace(selected_case_id)
            st.session_state["selected_case_id"] = ""
            st.success("案件已删除。")
            st.rerun()


def render_batch_review_page() -> None:
    st.header("批量复核")
    selected_case_id = _selected_case_id()
    st.caption("单个文件失败不会影响其他文件。批量过程不会保存完整文书内容。")
    files = st.file_uploader("批量上传 DOCX / PDF", type=["docx", "pdf"], accept_multiple_files=True)
    col1, col2 = st.columns(2)
    with col1:
        base_file = st.file_uploader("上传基础信息表（XLSX，可选）", type=["xlsx"], key="batch_base")
    with col2:
        evidence_file = st.file_uploader("上传证据目录（XLSX，可选）", type=["xlsx"], key="batch_evidence")
    enable_ocr = st.checkbox("批量 PDF 启用 OCR", value=False)

    if st.button("开始批量复核", type="primary"):
        temp_paths: list[Path] = []
        try:
            inputs: list[BatchInputFile] = []
            for uploaded in files or []:
                path = _save_upload(uploaded)
                temp_paths.append(path)
                inputs.append(BatchInputFile(path=path, file_name=uploaded.name, file_size=uploaded.size))
            base_path = _save_upload(base_file) if base_file is not None else None
            evidence_path = _save_upload(evidence_file) if evidence_file is not None else None
            temp_paths.extend([path for path in [base_path, evidence_path] if path is not None])
            results = run_batch_review(inputs, base_path, evidence_path, case_id=selected_case_id, enable_ocr=enable_ocr)
            st.session_state["batch_results"] = results
        finally:
            _cleanup(temp_paths)

    results = st.session_state.get("batch_results", [])
    if results:
        st.subheader("批量结果汇总")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "文件名": item.file_name,
                        "模式": item.mode_label,
                        "review_id": item.review_id or "",
                        "findings 数": item.finding_count,
                        "high": item.high_count,
                        "medium": item.medium_count,
                        "low": item.low_count,
                        "外部复核字段数": item.external_field_count,
                        "状态": item.status,
                        "错误原因": item.error or "",
                    }
                    for item in results
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_history_page() -> None:
    st.header("历史复核记录")
    case_id = _selected_case_id()
    only_current_case = st.checkbox("仅查看当前案件", value=bool(case_id), disabled=not bool(case_id))
    rows = list_review_runs(case_id=case_id if only_current_case else None)
    if not rows:
        st.info("暂无历史复核记录。")
        return
    st.dataframe(pd.DataFrame([row.model_dump(mode="json") for row in rows]), use_container_width=True, hide_index=True)
    selected_review = st.selectbox("选择 review_id 查看详情", [row.review_id for row in rows])
    detail = get_review_run_detail(selected_review)
    if not detail:
        st.error("未找到该历史记录。")
        return
    _store_current_review(detail.review_id, detail.findings, detail.external_fields, detail.manual_records, detail.mode_label)
    st.session_state["config_version"] = detail.config_version
    st.session_state["document_profile"] = detail.document_profile
    st.info("历史记录未保存原文书正文，因此只能重新导出摘要和复核包，不能生成 Word 复核提示版。")
    _render_review_result()
    st.subheader("删除历史记录")
    confirm = st.checkbox("我确认删除该历史记录", key=f"confirm_delete_{selected_review}")
    if st.button("删除该历史记录", disabled=not confirm):
        delete_review_run(selected_review)
        st.success("历史记录已删除。")
        st.rerun()


def render_settings_page() -> None:
    st.header("设置 / 规则说明")
    st.markdown(
        """
        - 本工具默认本地运行，不上传文件到第三方服务。
        - 所有 findings 都是“建议人工复核”的线索，不构成法律意见。
        - 案件工作区只保存案件信息、文书元数据、复核结果、待外部复核字段和人工记录，不保存完整原文书正文。
        - 案件内字段差异提示仅表示不同文书之间字段不一致，需人工判断是否属于正常版本差异。
        """
    )


def render_rule_config_page() -> None:
    st.header("规则配置中心")
    config = load_review_config_with_status()
    if config.fallback_used:
        st.warning("当前配置文件不可用或损坏，系统已回退到默认配置。")
    st.subheader("当前规则概览")
    overview = {
        "已启用风险类型": len(config.enabled_risk_types),
        "文书类型模板数量": len(config.document_profiles),
        "字段词典数量": len(config.field_dictionary),
        "占位符模式数量": len(config.placeholder_patterns),
        "外部复核来源配置数量": len(config.external_review_sources),
        "配置文件路径": config.config_path or str(DEFAULT_CONFIG_PATH),
        "是否使用默认配置 fallback": config.fallback_used,
        "配置版本": config.config_version,
    }
    st.json(overview)

    st.subheader("风险类型开关")
    st.caption("禁用风险类型可能导致某些问题不再提示，不会删除历史记录。")
    enabled = st.multiselect("启用的风险类型", sorted(VALID_RISK_TYPES), default=config.enabled_risk_types or sorted(VALID_RISK_TYPES))

    st.subheader("Severity 映射配置")
    severity_rows = []
    for risk_type in sorted(VALID_RISK_TYPES):
        severity_rows.append({"风险类型": risk_type, "默认等级": config.severity_for(risk_type, "medium")})
    severity_df = st.data_editor(pd.DataFrame(severity_rows), use_container_width=True, hide_index=True, column_config={"默认等级": st.column_config.SelectboxColumn("默认等级", options=["low", "medium", "high"])})

    st.subheader("占位符模式配置")
    placeholder_text = st.text_area("每行一个占位符或正则模式", value="\n".join(config.placeholder_patterns), height=140)

    st.subheader("外部复核来源配置")
    st.caption("suggested_action 必须包含“建议人工复核”，不得包含绝对化错误判断或法律结论。")
    source_key = st.selectbox("字段类型", sorted(config.external_review_sources))
    source_rule = config.external_review_sources[source_key]
    sources_text = st.text_area("复核来源，每行一个", value="\n".join(source_rule.sources), key="sources_text")
    action_text = st.text_area("建议动作", value=source_rule.suggested_action, key="action_text")

    st.subheader("文书类型模板")
    profile_key = st.selectbox("查看模板", sorted(config.document_profiles))
    st.json(config.document_profiles[profile_key].model_dump())

    st.subheader("字段词典管理")
    field_key = st.selectbox("查看字段", sorted(config.field_dictionary))
    field_config = config.field_dictionary[field_key]
    st.json(field_config.model_dump())
    alias_text = st.text_area("字段 alias，每行一个", value="\n".join(field_config.aliases), key="alias_text")

    if st.button("保存当前页面配置", type="primary"):
        payload = config.model_dump(exclude={"fallback_used", "config_path"}, mode="json")
        payload["enabled_risk_types"] = enabled
        payload["severity_mapping"] = {row["风险类型"]: row["默认等级"] for row in severity_df.to_dict("records")}
        payload["severity_overrides"] = payload["severity_mapping"]
        payload["placeholder_patterns"] = [line.strip() for line in placeholder_text.splitlines() if line.strip()]
        payload["external_review_sources"][source_key]["sources"] = [line.strip() for line in sources_text.splitlines() if line.strip()]
        payload["external_review_sources"][source_key]["suggested_action"] = action_text.strip()
        payload["field_dictionary"][field_key]["aliases"] = [line.strip() for line in alias_text.splitlines() if line.strip()]
        try:
            validate_config_data(payload)
            temp_path = Path("data") / "review_rules_import.yml"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            import yaml
            temp_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
            import_rules_with_history(temp_path, change_note="规则配置中心保存")
            load_review_config.cache_clear()
            st.success("规则配置已保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"配置校验失败：{exc}")

    st.subheader("导入 / 导出 / 恢复默认")
    export_text = export_config(config)
    st.download_button("导出当前规则配置", data=export_text.encode("utf-8"), file_name=f"review_rules_export_{_download_suffix()}.yml", mime="text/yaml")
    uploaded = st.file_uploader("导入 YAML / JSON 配置", type=["yml", "yaml", "json"])
    if uploaded is not None and st.button("校验并导入配置"):
        temp_path = Path("data") / f"uploaded_rules{Path(uploaded.name).suffix}"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(uploaded.getvalue())
        try:
            import_rules_with_history(temp_path, change_note="UI 导入规则配置")
            st.success("配置导入成功。")
            st.rerun()
        except Exception as exc:
            st.error(f"配置导入失败，旧配置未覆盖：{exc}")
    confirm_restore = st.checkbox("我确认恢复默认规则配置")
    if st.button("恢复默认规则配置", disabled=not confirm_restore):
        restore_default_rules_with_history()
        load_review_config.cache_clear()
        st.success("已恢复默认规则配置。")
        st.rerun()

    st.subheader("最近 10 次配置变更")
    history = list_rule_config_history()
    if history:
        st.dataframe(pd.DataFrame([item.model_dump(mode="json") for item in history]), use_container_width=True, hide_index=True)
    else:
        st.info("暂无配置变更记录。")


st.title("律师文书基础信息复核助手 Demo")
st.caption("本工具仅用于辅助复核，最终判断由人工完成；默认本地运行，不上传文件到第三方服务。")
st.warning("本工具只做基础信息和关键事实复核，不构成法律意见；未发现明显复核项也不代表文书无误。")

with st.sidebar:
    page = st.radio("功能", ["单次复核", "案件工作区", "批量复核", "历史记录", "规则配置", "设置"])
    _render_case_selector()
    st.header("示例数据")
    st.code("app/sample_data/sample_document.docx\napp/sample_data/sample_base_info.xlsx\napp/sample_data/sample_evidence_index.xlsx")

if page == "单次复核":
    render_single_review_page()
elif page == "案件工作区":
    render_case_workspace_page()
elif page == "批量复核":
    render_batch_review_page()
elif page == "历史记录":
    render_history_page()
elif page == "规则配置":
    render_rule_config_page()
else:
    render_settings_page()
