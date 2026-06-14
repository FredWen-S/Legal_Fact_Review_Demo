from __future__ import annotations

import re

from app.models.schemas import ExtractedItem, ReviewFinding, TextChunk
from app.utils import stable_id


CASE_NO_PATTERN = re.compile(r"^[（(]\d{4}[）)][\u4e00-\u9fa5A-Za-z0-9]+(?:初|终|申|执|民|商|行|刑)[\u4e00-\u9fa5A-Za-z0-9]*号$")
ID_PATTERN = re.compile(r"^\d{17}[\dXx]$")
CREDIT_CODE_PATTERN = re.compile(r"^[0-9A-Z]{18}$")
DATE_PATTERN = re.compile(r"^\d{4}年(0?[1-9]|1[0-2])月(0?[1-9]|[12]\d|3[01])日$")
AMOUNT_PATTERN = re.compile(r"^(?:人民币)?[0-9][0-9,]*(?:\.\d+)?\s*元$")


def check_placeholders(items: list[ExtractedItem]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    for item in items:
        if item.field_name == "文书中的占位符":
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("placeholder", item.value, item.source_location),
                    risk_type="PLACEHOLDER_REMAINING",
                    severity="high",
                    field_name=item.field_name,
                    document_value=item.value,
                    reference_value=None,
                    source_location=item.source_location,
                    confidence=0.95,
                    reason=f"文书中残留模板占位内容“{item.value}”，该处内容尚不完整或未替换。",
                    suggested_action="建议人工复核该占位符是否应删除、补充或替换为正式内容。",
                )
            )
    return findings


def check_format_errors(items: list[ExtractedItem], chunks: list[TextChunk]) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    checks = {
        "案号": CASE_NO_PATTERN,
        "身份证号": ID_PATTERN,
        "统一社会信用代码": CREDIT_CODE_PATTERN,
        "日期": DATE_PATTERN,
        "金额": AMOUNT_PATTERN,
    }
    for item in items:
        pattern = checks.get(item.field_name)
        if pattern and not pattern.match(item.value):
            findings.append(_format_finding(item, f"{item.field_name}格式疑似异常。"))

    for item in items:
        if item.field_name == "案号原文" and not CASE_NO_PATTERN.match(item.value):
            findings.append(_format_finding(item, "案号原文不符合常见案号格式。"))

    for chunk in chunks:
        for bad_case_no in re.findall(r"案号[:：]\s*([^\s，。；;]+)", chunk.text):
            if not CASE_NO_PATTERN.match(bad_case_no):
                findings.append(
                    ReviewFinding(
                        risk_id=stable_id("case-format", bad_case_no, chunk.location),
                        risk_type="FORMAT_ERROR",
                        severity="medium",
                        field_name="案号",
                        document_value=bad_case_no,
                        reference_value=None,
                        source_location=chunk.location,
                        confidence=0.8,
                        reason="案号格式与常见法院案号格式不一致。",
                        suggested_action="建议人工复核立案材料或法院文书，确认案号的年份、字号和编号是否完整。",
                    )
                )
    return _dedupe(findings)


def _format_finding(item: ExtractedItem, reason: str) -> ReviewFinding:
    return ReviewFinding(
        risk_id=stable_id("format", item.field_name, item.value, item.source_location),
        risk_type="FORMAT_ERROR",
        severity="medium",
        field_name=item.field_name.replace("原文", ""),
        document_value=item.value,
        reference_value=None,
        source_location=item.source_location,
        confidence=0.82,
        reason=reason,
        suggested_action="建议人工复核该字段格式，并与原始材料或立案信息核对。",
    )


def _dedupe(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[str] = set()
    result: list[ReviewFinding] = []
    for finding in findings:
        key = f"{finding.risk_type}|{finding.field_name}|{finding.document_value}|{finding.source_location}"
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return result
