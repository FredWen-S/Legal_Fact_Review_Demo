from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrivacyPolicy:
    redact_storage_metadata: bool = True
    redact_report_sensitive_fields: bool = False
    include_privacy_summary_in_exports: bool = True
    mask_company_names: bool = False
    max_error_length: int = 300
    max_metadata_value_length: int = 500


def default_privacy_policy() -> PrivacyPolicy:
    return PrivacyPolicy()
