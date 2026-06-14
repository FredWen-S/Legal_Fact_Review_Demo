from __future__ import annotations

import html

from app.models.schemas import ExtractedReviewField, ManualReviewRecord, ReviewFinding
from app.reports.excel_report import external_fields_to_dataframe, findings_to_dataframe, manual_records_to_dataframe


def build_html_report(
    findings: list[ReviewFinding],
    external_fields: list[ExtractedReviewField] | None = None,
    manual_records: list[ManualReviewRecord] | None = None,
    mode_label: str = "完整复核模式",
) -> str:
    df = findings_to_dataframe(findings)
    table_html = df.to_html(index=False, escape=True)
    external_df = external_fields_to_dataframe(external_fields or [])
    external_table_html = external_df.to_html(index=False, escape=True)
    manual_df = manual_records_to_dataframe(manual_records or [])
    manual_table_html = manual_df.to_html(index=False, escape=True, classes="manual-records")
    high = sum(1 for item in findings if item.severity == "high")
    medium = sum(1 for item in findings if item.severity == "medium")
    low = sum(1 for item in findings if item.severity == "low")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>律师文书基础信息复核报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2937; }}
    h1 {{ font-size: 24px; }}
    .notice {{ padding: 12px 16px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; }}
    .summary span {{ display: inline-block; margin-right: 16px; font-weight: 600; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    .manual-records td:nth-child(3) {{ font-weight: 600; color: #9a3412; }}
  </style>
</head>
<body>
  <h1>{html.escape("律师文书基础信息复核报告")}</h1>
  <p class="notice">本工具仅用于辅助复核，所有发现均为建议人工复核的线索，不构成法律意见，最终判断由人工完成。</p>
  <p><strong>当前模式：</strong>{html.escape(mode_label)}</p>
  <p class="summary"><span>高风险：{high}</span><span>中风险：{medium}</span><span>低风险：{low}</span><span>总计：{len(findings)}</span></p>
  <h2>复核发现</h2>
  {table_html}
  <h2>待外部复核字段清单</h2>
  <p class="notice">本清单仅基于当前文书自动抽取生成，用于提示人工复核，不代表系统已完成外部核验。</p>
  {external_table_html}
  <h2>人工复核记录</h2>
  <p class="notice">人工复核记录由用户填写，用于形成工作底稿；状态为“需修改”时请重点查看人工确认值。</p>
  {manual_table_html}
</body>
</html>"""
