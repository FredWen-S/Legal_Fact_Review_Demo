from app.config.review_config import load_review_config
from app.models.schemas import BaseInfoItem, EvidenceItem, TextChunk
from app.review_engine import review_document


def test_review_config_loads_defaults():
    config = load_review_config()
    assert "PLACEHOLDER_REMAINING" in config.enabled_risk_types
    assert "当事人名称" in config.critical_fields


def test_review_engine_respects_disabled_risk_type(tmp_path):
    config_path = tmp_path / "rules.yml"
    config_path.write_text(
        "enabled_risk_types:\n  - EVIDENCE_REFERENCE_MISSING\ncritical_fields: []\nplaceholder_patterns:\n  - 待补充\n",
        encoding="utf-8",
    )
    config = load_review_config(str(config_path))
    findings = review_document(
        [
            TextChunk(text="事项：待补充。", location="段落1"),
            TextChunk(text="证据7：催告函。", location="段落2"),
        ],
        [BaseInfoItem(field_name="法定代表人", standard_value="张三")],
        [EvidenceItem(evidence_no="1", evidence_name="合同")],
        config=config,
    )
    assert findings
    assert {finding.risk_type for finding in findings} == {"EVIDENCE_REFERENCE_MISSING"}
