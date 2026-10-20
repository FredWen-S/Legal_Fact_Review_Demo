from __future__ import annotations

from app.models.schemas import EvidenceItem, ExtractedItem, ReviewFinding
from app.utils import stable_id


CN_NUMBERS = {
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}


def check_evidence_references(items: list[ExtractedItem], evidence_index: list[EvidenceItem]) -> list[ReviewFinding]:
    existing = {_normalize_no(item.evidence_no) for item in evidence_index}
    findings: list[ReviewFinding] = []
    for item in items:
        if item.field_name != "证据编号":
            continue
        no = _normalize_no(item.value)
        if no and no not in existing:
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("evidence", no, item.source_location),
                    risk_type="EVIDENCE_REFERENCE_MISSING",
                    severity="high",
                    field_name="证据编号",
                    document_value=f"证据{no}",
                    reference_value="证据目录未列明",
                    source_location=item.source_location,
                    reference_source="证据目录",
                    confidence=0.9,
                    reason=f"正文引用了证据{no}，但证据目录中未找到对应编号。",
                    suggested_action="建议人工复核证据目录是否遗漏该编号，或确认正文引用编号是否需要调整。",
                )
            )
    return findings


def _normalize_no(value: str) -> str:
    clean = str(value).replace("证据", "").strip()
    return CN_NUMBERS.get(clean, clean)
