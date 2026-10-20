from __future__ import annotations

from app.privacy.policy import PrivacyPolicy
from app.privacy.redaction import build_privacy_summary, redact_text, sanitize_error, sanitize_metadata


def test_sanitize_metadata_removes_raw_text_and_llm_payload_keys():
    metadata = {
        "document_text": "完整正文不应落库",
        "extracted_text": "完整抽取文本不应落库",
        "raw_response": "完整 LLM response 不应落库",
        "prompt": "完整 prompt 不应落库",
        "llm_response": "另一个完整 LLM response",
        "nested": {"full_text": "嵌套正文", "safe": "ok"},
    }

    sanitized = sanitize_metadata(metadata)

    assert "document_text" not in sanitized
    assert "extracted_text" not in sanitized
    assert "raw_response" not in sanitized
    assert "prompt" not in sanitized
    assert "llm_response" not in sanitized
    assert sanitized["nested"] == {"safe": "ok"}


def test_sanitize_error_removes_traceback_and_truncates():
    traceback_text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "app/main.py", line 1, in <module>',
            "RuntimeError: " + "x" * 1000,
        ]
    )

    sanitized = sanitize_error(traceback_text, PrivacyPolicy(max_error_length=80))

    assert "Traceback" not in sanitized
    assert 'File "app/main.py"' not in sanitized
    assert sanitized.startswith("RuntimeError:")
    assert len(sanitized) <= 80


def test_redact_text_masks_email_phone_and_long_id_like_values():
    text = "contact test@example.com phone 13812345678 id 110101199001011234 code 91310000MA1K000001"

    redacted = redact_text(text)

    assert "test@example.com" not in redacted
    assert "13812345678" not in redacted
    assert "110101199001011234" not in redacted
    assert "91310000MA1K000001" not in redacted
    assert "te***@example.com" in redacted
    assert "138****5678" in redacted


def test_sanitize_metadata_truncates_long_values_and_masks_sensitive_keys():
    sanitized = sanitize_metadata(
        {
            "notes": "x" * 800,
            "registered_address": "上海市浦东新区示例路100号",
            "legal_representative": "张三",
            "company_name": "上海星河科技股份有限公司",
        },
        PrivacyPolicy(max_metadata_value_length=120),
    )

    assert len(sanitized["notes"]) <= 120
    assert sanitized["registered_address"] != "上海市浦东新区示例路100号"
    assert sanitized["legal_representative"] != "张三"
    assert sanitized["company_name"] == "上海星河科技股份有限公司"


def test_company_name_masking_is_optional():
    text = "上海星河科技股份有限公司"

    assert redact_text(text) == text
    assert redact_text(text, PrivacyPolicy(mask_company_names=True)) == "[redacted]"


def test_privacy_summary_can_be_generated():
    summary = build_privacy_summary()

    assert summary["scope"] == "This is a synthetic local demo."
    assert "metadata only" in summary["history_audit_storage"]
