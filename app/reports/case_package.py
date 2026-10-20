from __future__ import annotations

import html
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from app.models.schemas import CaseWorkspace, FieldDifference, ReviewRunDetail
from app.reports.excel_report import external_fields_to_dataframe, findings_to_dataframe, manual_records_to_dataframe
from app.reports.package_export import build_review_package_zip
from app.storage.sqlite_store import get_case_workspace, get_review_run_detail, list_review_runs
from app.workflows.case_differences import build_case_field_differences


def build_case_summary_excel(case: CaseWorkspace, details: list[ReviewRunDetail], differences: list[FieldDifference] | None = None) -> bytes:
    output = BytesIO()
    differences = differences or []
    case_info = pd.DataFrame(
        [
            ("案件名称", case.case_name),
            ("案件编号", case.internal_case_no or ""),
            ("客户名称", case.client_name or ""),
            ("对方主体", case.counterparty_name or ""),
            ("案件类型", case.case_type or ""),
            ("备注", case.note or ""),
            ("创建时间", case.created_at.isoformat(timespec="seconds")),
            ("更新时间", case.updated_at.isoformat(timespec="seconds")),
        ],
        columns=["项目", "内容"],
    )
    review_summary = pd.DataFrame(
        [
            {
                "review_id": detail.review_id,
                "文书文件名": detail.file_name or "",
                "复核模式": detail.mode_label,
                "findings 数": detail.finding_count,
                "high": detail.high_count,
                "medium": detail.medium_count,
                "low": detail.low_count,
                "外部复核字段数": detail.external_field_count,
                "人工复核记录数": detail.manual_record_count,
                "规则配置版本": detail.config_version or "",
                "文书类型模板": detail.document_profile or "",
                "创建时间": detail.created_at.isoformat(timespec="seconds"),
            }
            for detail in details
        ]
    )
    high_findings = [finding for detail in details for finding in detail.findings if finding.severity == "high"]
    external_fields = [field for detail in details for field in detail.external_fields]
    manual_records = [record for detail in details for record in detail.manual_records]
    modify_records = [record for record in manual_records if record.review_status == "需修改"]
    diff_df = pd.DataFrame([difference.model_dump() for difference in differences])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        case_info.to_excel(writer, index=False, sheet_name="案件信息")
        review_summary.to_excel(writer, index=False, sheet_name="文书复核汇总")
        findings_to_dataframe(high_findings).to_excel(writer, index=False, sheet_name="全部 high 风险")
        external_fields_to_dataframe(external_fields).to_excel(writer, index=False, sheet_name="全部待外部复核字段")
        manual_records_to_dataframe(manual_records).to_excel(writer, index=False, sheet_name="全部人工复核记录")
        manual_records_to_dataframe(modify_records).to_excel(writer, index=False, sheet_name="需修改字段清单")
        diff_df.to_excel(writer, index=False, sheet_name="案件内字段差异")
        for worksheet in writer.sheets.values():
            for column_cells in worksheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 12), 42)
    return output.getvalue()


def build_case_html_report(case: CaseWorkspace, details: list[ReviewRunDetail], differences: list[FieldDifference] | None = None) -> str:
    differences = differences or []
    total_findings = sum(detail.finding_count for detail in details)
    high = sum(detail.high_count for detail in details)
    medium = sum(detail.medium_count for detail in details)
    low = sum(detail.low_count for detail in details)
    summary_rows = "".join(
        f"<tr><td>{html.escape(detail.review_id)}</td><td>{html.escape(detail.file_name or '')}</td><td>{html.escape(detail.mode_label)}</td>"
        f"<td>{detail.finding_count}</td><td>{detail.high_count}</td><td>{detail.medium_count}</td><td>{detail.low_count}</td>"
        f"<td>{detail.external_field_count}</td><td>{detail.manual_record_count}</td><td>{html.escape(detail.config_version or '')}</td><td>{html.escape(detail.document_profile or '')}</td></tr>"
        for detail in details
    )
    diff_rows = "".join(
        f"<tr><td>{html.escape(item.field_type)}</td><td>{html.escape(item.left_value)}</td><td>{html.escape(item.right_value)}</td>"
        f"<td>{html.escape(item.documents)}</td><td>{html.escape(item.suggested_action)}</td></tr>"
        for item in differences
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>案件复核报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    .notice {{ padding: 12px 16px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; }}
    .summary span {{ display: inline-block; margin-right: 16px; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>案件复核报告：{html.escape(case.case_name)}</h1>
  <p class="notice">本报告仅用于辅助人工复核，不构成法律意见。案件内字段差异提示仅表示不同文书之间字段不一致，需人工判断是否属于正常版本差异。</p>
  <p><strong>案件编号：</strong>{html.escape(case.internal_case_no or '')}</p>
  <p><strong>客户名称：</strong>{html.escape(case.client_name or '')}</p>
  <p><strong>对方主体：</strong>{html.escape(case.counterparty_name or '')}</p>
  <p class="summary"><span>文书数：{len(details)}</span><span>findings：{total_findings}</span><span>high：{high}</span><span>medium：{medium}</span><span>low：{low}</span></p>
  <h2>文书复核汇总</h2>
  <table><thead><tr><th>review_id</th><th>文书文件名</th><th>模式</th><th>findings</th><th>high</th><th>medium</th><th>low</th><th>外部字段</th><th>人工记录</th><th>规则配置版本</th><th>文书类型模板</th></tr></thead><tbody>{summary_rows}</tbody></table>
  <h2>案件内字段差异提示</h2>
  <table><thead><tr><th>字段类型</th><th>文书 A 值</th><th>文书 B 值</th><th>涉及文书</th><th>建议动作</th></tr></thead><tbody>{diff_rows}</tbody></table>
</body>
</html>"""


def build_case_review_package_zip(case_id: str, db_path: str = "data/review_runs.sqlite") -> bytes:
    case = get_case_workspace(case_id, path=db_path)
    if case is None:
        raise ValueError(f"Case workspace not found: {case_id}")
    details = [detail for summary in list_review_runs(case_id=case_id, path=db_path) if (detail := get_review_run_detail(summary.review_id, path=db_path))]
    differences = build_case_field_differences(case_id, db_path)
    excel_bytes = build_case_summary_excel(case, details, differences)
    html_report = build_case_html_report(case, details, differences)

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("案件复核汇总.xlsx", excel_bytes)
        package.writestr("案件复核报告.html", html_report.encode("utf-8"))
        for detail in details:
            single_package = build_review_package_zip(
                detail.findings,
                detail.external_fields,
                detail.manual_records,
                review_id=detail.review_id,
                mode_label=detail.mode_label,
                structured_extraction=detail.structured_extraction,
                knowledge_context=detail.knowledge_context,
            )
            with ZipFile(BytesIO(single_package)) as single_zip:
                for name in single_zip.namelist():
                    package.writestr(f"单份文书复核包/review_{detail.review_id}/{name}", single_zip.read(name))
    return output.getvalue()
