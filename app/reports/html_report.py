from __future__ import annotations

import html

from app.models.schemas import (
    ExtractedReviewField,
    KnowledgeContext,
    ManualReviewRecord,
    ReviewFinding,
    StructuredExtractionResult,
)
from app.privacy.policy import PrivacyPolicy, default_privacy_policy
from app.privacy.redaction import build_privacy_summary
from app.reports.excel_report import (
    external_fields_to_dataframe,
    findings_to_dataframe,
    knowledge_context_to_dataframe,
    manual_records_to_dataframe,
    structured_extraction_to_dataframe,
)


DISCLAIMER = (
    "This demo is for legal-document review assistance only. "
    "All issues are review suggestions, not legal conclusions. "
    "All knowledge-base records in this project are synthetic. "
    "本报告仅用于辅助人工复核，所有发现均为建议人工复核的线索，不构成法律意见，最终判断由人工完成。"
)


def build_html_report(
    findings: list[ReviewFinding],
    external_fields: list[ExtractedReviewField] | None = None,
    manual_records: list[ManualReviewRecord] | None = None,
    mode_label: str = "Complete Review",
    config_version: str | None = None,
    document_profile: str | None = None,
    config_updated_at: str | None = None,
    structured_extraction: StructuredExtractionResult | None = None,
    knowledge_context: KnowledgeContext | None = None,
    privacy_policy: PrivacyPolicy | None = None,
) -> str:
    policy = privacy_policy or default_privacy_policy()
    issues_df = findings_to_dataframe(findings, policy)
    workbench_df = external_fields_to_dataframe(external_fields or [], policy)
    manual_df = manual_records_to_dataframe(manual_records or [], policy)
    extraction_df = structured_extraction_to_dataframe(structured_extraction, policy)
    knowledge_df = knowledge_context_to_dataframe(knowledge_context, policy)
    privacy_summary = build_privacy_summary(policy)
    privacy_section = _privacy_summary_html(privacy_summary) if policy.include_privacy_summary_in_exports else ""

    high = sum(1 for item in findings if item.severity == "high")
    medium = sum(1 for item in findings if item.severity == "medium")
    low = sum(1 for item in findings if item.severity == "low")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>LLM + RAG Legal Review Report</title>
  <style>
    :root {{
      --ink: #172033;
      --muted: #667085;
      --panel: #f8fafc;
      --line: #d8dee7;
      --accent: #0f766e;
      --warn: #b45309;
    }}
    body {{ font-family: "Segoe UI", "Helvetica Neue", sans-serif; margin: 32px; color: var(--ink); line-height: 1.5; }}
    h1, h2 {{ letter-spacing: 0.01em; }}
    .notice {{ padding: 14px 16px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 10px; color: #7c2d12; }}
    .meta {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 18px 0 24px; }}
    .card {{ background: linear-gradient(180deg, #ffffff, var(--panel)); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }}
    .card .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .card .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 14px; font-size: 13px; }}
    th, td {{ border: 1px solid var(--line); padding: 8px; vertical-align: top; text-align: left; }}
    th {{ background: #eef2f7; }}
    .muted {{ color: var(--muted); }}
  </style>
</head>
<body>
  <h1>LLM + RAG Legal Document Review Report / 法律文书审查报告</h1>
  <p class="notice">{html.escape(DISCLAIMER)}</p>
  <p><strong>Review Mode:</strong> {html.escape(mode_label)}<br>
     <strong>Document Profile:</strong> {html.escape(document_profile or "general")}<br>
     <strong>Config Version:</strong> {html.escape(config_version or "default")}<br>
     <strong>Config Updated At:</strong> {html.escape(config_updated_at or "")}<br>
     <strong>Extraction Mode:</strong> {html.escape(structured_extraction.mode if structured_extraction else "n/a")}<br>
     <strong>Extraction Model:</strong> {html.escape(structured_extraction.model_name or "n/a") if structured_extraction else "n/a"}</p>

  <div class="meta">
    <div class="card"><div class="label">Issues</div><div class="value">{len(findings)}</div></div>
    <div class="card"><div class="label">High</div><div class="value">{high}</div></div>
    <div class="card"><div class="label">Medium</div><div class="value">{medium}</div></div>
    <div class="card"><div class="label">Low</div><div class="value">{low}</div></div>
  </div>

  <h2>Issues / 复核发现</h2>
  {issues_df.to_html(index=False, escape=True)}

  <h2>Structured Extraction / 结构化抽取</h2>
  <p class="muted">Structured entities are extracted by the configured LLM when an API key is available, otherwise by the local mock extractor.</p>
  {extraction_df.to_html(index=False, escape=True)}

  <h2>Retrieved Knowledge / 检索知识</h2>
  <p class="muted">Retrieval uses only synthetic knowledge-base records stored in this project.</p>
  {knowledge_df.to_html(index=False, escape=True)}

  <h2>Review Workbench / 待外部复核字段清单</h2>
  {workbench_df.to_html(index=False, escape=True)}

  <h2>Manual Review Notes / 人工复核记录</h2>
  {manual_df.to_html(index=False, escape=True)}

  {privacy_section}
</body>
</html>"""


def _privacy_summary_html(summary: dict[str, str]) -> str:
    rows = "\n".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(value)}</td></tr>"
        for key, value in summary.items()
    )
    return f"""
  <h2>Privacy Summary / 隐私摘要</h2>
  <p class="muted">Local privacy policy summary for this synthetic demo export.</p>
  <table>{rows}</table>
"""
