from __future__ import annotations

import re
from typing import Any

from app.privacy.policy import PrivacyPolicy, default_privacy_policy


REMOVED_VALUE = "[removed by privacy policy]"
MASK = "[redacted]"

BLOCKED_METADATA_KEYS = {
    "document_text",
    "full_text",
    "raw_text",
    "source_text",
    "original_text",
    "extracted_text",
    "raw_response",
    "llm_response",
    "full_response",
    "prompt",
    "system_prompt",
    "user_prompt",
    "messages",
}

SENSITIVE_KEYWORDS = {
    "credit_code",
    "unified_social_credit_code",
    "social_credit_code",
    "id_number",
    "identity_number",
    "phone",
    "mobile",
    "email",
    "registered_address",
    "address",
    "legal_representative",
    "法定代表人",
    "统一社会信用代码",
    "身份证号",
    "手机号",
    "电话",
    "邮箱",
    "住所地",
    "注册地址",
}

EMAIL_RE = re.compile(r"(?<![\w.%-])[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LONG_ID_RE = re.compile(r"(?<![A-Z0-9])(?:\d{17}[\dXx]|[0-9A-Z]{18}|\d{12,})(?![A-Z0-9])")
CREDIT_CODE_RE = re.compile(r"(?<![A-Z0-9])[0-9A-Z]{18}(?![A-Z0-9])")


def redact_text(value: str, policy: PrivacyPolicy | None = None) -> str:
    policy = policy or default_privacy_policy()
    text = _compact_text(str(value), policy.max_metadata_value_length)
    text = EMAIL_RE.sub(_mask_email, text)
    text = PHONE_RE.sub(_mask_phone, text)
    text = CREDIT_CODE_RE.sub(_mask_long_token, text)
    text = LONG_ID_RE.sub(_mask_long_token, text)
    if policy.mask_company_names:
        text = re.sub(r"[\u4e00-\u9fffA-Za-z0-9（）()]{2,40}(?:公司|集团|律所|事务所)", MASK, text)
    return text


def sanitize_metadata(metadata: dict[str, Any], policy: PrivacyPolicy | None = None) -> dict[str, Any]:
    policy = policy or default_privacy_policy()
    if not policy.redact_storage_metadata:
        return _truncate_metadata(metadata, policy)
    sanitized = _sanitize_value(metadata, policy, parent_key="")
    return sanitized if isinstance(sanitized, dict) else {}


def sanitize_error(error: str, policy: PrivacyPolicy | None = None) -> str:
    policy = policy or default_privacy_policy()
    text = _summarize_traceback(str(error))
    return redact_text(_compact_text(text, policy.max_error_length), policy)


def build_privacy_summary(policy: PrivacyPolicy | None = None) -> dict[str, str]:
    policy = policy or default_privacy_policy()
    return {
        "scope": "This is a synthetic local demo.",
        "legal_advice": "No production legal advice is provided.",
        "history_audit_storage": "Review history and audit log store metadata only.",
        "not_stored": "Full document text, full extracted text, prompts, and full LLM responses are not stored by history/audit.",
        "storage_redaction": "Storage/audit metadata redaction is enabled." if policy.redact_storage_metadata else "Storage/audit metadata redaction is disabled.",
        "report_redaction": "Report sensitive-field redaction is enabled." if policy.redact_report_sensitive_fields else "Report findings are not forcibly redacted beyond existing field-level masking.",
    }


def _sanitize_value(value: Any, policy: PrivacyPolicy, parent_key: str) -> Any:
    normalized_key = parent_key.strip().lower()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = _compact_text(str(key), 120)
            if _is_blocked_key(key_text):
                continue
            cleaned = _sanitize_value(item, policy, key_text)
            if cleaned is not None:
                result[key_text] = cleaned
        return result
    if isinstance(value, list):
        return [_sanitize_value(item, policy, parent_key) for item in value[:30] if item is not None]
    if isinstance(value, tuple):
        return [_sanitize_value(item, policy, parent_key) for item in value[:30] if item is not None]
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if value is None:
        return None
    text = sanitize_error(str(value), policy) if "error" in normalized_key else redact_text(str(value), policy)
    if _is_sensitive_key(parent_key):
        return _mask_named_sensitive_value(text)
    return text


def _truncate_metadata(metadata: dict[str, Any], policy: PrivacyPolicy) -> dict[str, Any]:
    def truncate(value: Any) -> Any:
        if isinstance(value, dict):
            return {_compact_text(str(key), 120): truncate(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [truncate(item) for item in value[:30] if item is not None]
        if isinstance(value, tuple):
            return [truncate(item) for item in value[:30] if item is not None]
        if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
            return value
        if value is None:
            return None
        return _compact_text(str(value), policy.max_metadata_value_length)

    return truncate(metadata)


def _is_blocked_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in BLOCKED_METADATA_KEYS or any(blocked in normalized for blocked in BLOCKED_METADATA_KEYS)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(keyword.lower() in normalized for keyword in SENSITIVE_KEYWORDS)


def _mask_named_sensitive_value(value: str) -> str:
    if not value:
        return value
    if "@" in value:
        return EMAIL_RE.sub(_mask_email, value)
    if len(value) <= 6:
        return MASK
    return value[:2] + "*" * min(max(len(value) - 4, 4), 12) + value[-2:]


def _summarize_traceback(text: str) -> str:
    if "Traceback (most recent call last)" not in text:
        return text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if not line.startswith("File ") and not line.startswith("Traceback"):
            return line
    return "Error details omitted."


def _compact_text(value: str, max_length: int) -> str:
    text = value.replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _mask_email(match: re.Match[str]) -> str:
    value = match.group(0)
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def _mask_phone(match: re.Match[str]) -> str:
    value = match.group(0)
    digits = re.sub(r"\D", "", value)
    if digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    return digits[:3] + "****" + digits[-4:]


def _mask_long_token(match: re.Match[str]) -> str:
    value = match.group(0)
    if len(value) <= 8:
        return MASK
    return value[:4] + "*" * max(4, len(value) - 8) + value[-4:]
