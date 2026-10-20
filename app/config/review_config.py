from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


DEFAULT_CONFIG_PATH = Path(__file__).with_name("review_rules.yml")
VALID_RISK_TYPES = {
    "MISSING_FIELD",
    "INTERNAL_CONFLICT",
    "SOURCE_MISMATCH",
    "FORMAT_ERROR",
    "POSSIBLY_OUTDATED",
    "PLACEHOLDER_REMAINING",
    "EVIDENCE_REFERENCE_MISSING",
    "AMOUNT_INCONSISTENCY",
    "DATE_LOGIC_WARNING",
    "SPELLING_VARIATION",
    "CLAUSE_NUMBERING_ERROR",
    "CLIENT_PROFILE_MISMATCH",
    "MISSING_STANDARD_CLAUSE",
    "TEMPLATE_FIELD_MISMATCH",
    "STATUTE_REPEALED",
    "STATUTE_ARTICLE_OUT_OF_RANGE",
    "STATUTE_UNVERIFIED",
}
VALID_SEVERITIES = {"low", "medium", "high"}
FORBIDDEN_ACTION_TERMS = ["系统确认错误", "系统已确认", "确认错误", "法律上必然", "法律上无效", "自动核验通过", "已完成外部核验", "替代律师判断"]


class ExternalReviewSourceConfig(BaseModel):
    sources: list[str] = Field(default_factory=list)
    suggested_action: str = "建议人工复核该字段是否与外部基础材料一致。"

    @field_validator("sources")
    @classmethod
    def clean_sources(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("suggested_action")
    @classmethod
    def action_must_be_safe(cls, value: str) -> str:
        if "建议人工复核" not in value:
            raise ValueError("suggested_action 必须包含“建议人工复核”")
        if any(term in value for term in FORBIDDEN_ACTION_TERMS):
            raise ValueError("suggested_action 不得包含绝对化法律结论或系统确认表述")
        return value


class DocumentProfileConfig(BaseModel):
    display_name: str
    required_fields: list[str] = Field(default_factory=list)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)
    amount_keywords: list[str] = Field(default_factory=list)
    date_keywords: list[str] = Field(default_factory=list)
    evidence_keywords: list[str] = Field(default_factory=list)


class FieldConfig(BaseModel):
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    regex_patterns: list[str] = Field(default_factory=list)
    suggested_review_sources: list[str] = Field(default_factory=list)
    default_severity: Literal["low", "medium", "high"] = "medium"
    required_by_default: bool = False

    @field_validator("regex_patterns")
    @classmethod
    def regex_patterns_must_compile(cls, value: list[str]) -> list[str]:
        cleaned = [str(pattern).strip() for pattern in value if str(pattern).strip()]
        _validate_regex_patterns(cleaned, "field_dictionary.regex_patterns")
        return cleaned


class ReviewRulesConfig(BaseModel):
    config_version: str = "default-v1"
    updated_at: str | None = None
    updated_by: str = "local_user"
    enabled_risk_types: list[str] = Field(default_factory=list)
    critical_fields: list[str] = Field(default_factory=list)
    severity_mapping: dict[str, Literal["low", "medium", "high"]] = Field(default_factory=dict)
    severity_overrides: dict[str, Literal["low", "medium", "high"]] = Field(default_factory=dict)
    placeholder_patterns: list[str] = Field(default_factory=list)
    external_review_sources: dict[str, ExternalReviewSourceConfig] = Field(default_factory=dict)
    document_profiles: dict[str, DocumentProfileConfig] = Field(default_factory=dict)
    field_dictionary: dict[str, FieldConfig] = Field(default_factory=dict)
    fallback_used: bool = False
    config_path: str | None = None

    @field_validator("enabled_risk_types")
    @classmethod
    def risk_types_must_be_valid(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - VALID_RISK_TYPES)
        if invalid:
            raise ValueError(f"非法风险类型：{', '.join(invalid)}")
        return value

    @field_validator("placeholder_patterns")
    @classmethod
    def clean_placeholders(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        _validate_regex_patterns(cleaned, "placeholder_patterns")
        return cleaned

    @model_validator(mode="after")
    def merge_legacy_severity(self):
        merged = dict(self.severity_mapping)
        merged.update(self.severity_overrides)
        self.severity_mapping = merged
        self.severity_overrides = merged
        return self

    def risk_enabled(self, risk_type: str) -> bool:
        return not self.enabled_risk_types or risk_type in self.enabled_risk_types

    def severity_for(self, risk_type: str, default: str) -> str:
        configured = self.severity_mapping.get(risk_type, default)
        return configured if configured in VALID_SEVERITIES else default

    def external_review_rule(self, key: str) -> dict[str, Any]:
        rule = self.external_review_sources.get(key) or self.external_review_sources.get(_legacy_rule_key(key))
        if rule:
            return rule.model_dump()
        return DEFAULT_EXTERNAL_REVIEW_SOURCES.get(key, DEFAULT_EXTERNAL_REVIEW_SOURCES["default"]).model_dump()

    def profile(self, document_profile: str | None) -> DocumentProfileConfig:
        if document_profile and document_profile in self.document_profiles:
            return self.document_profiles[document_profile]
        return self.document_profiles.get("general", default_config().document_profiles["general"])

    def critical_fields_for_profile(self, document_profile: str | None = None) -> list[str]:
        profile = self.profile(document_profile)
        mapped = [_profile_field_to_extracted(field) for field in profile.required_fields]
        fields = mapped or self.critical_fields
        return [field for field in fields if field]


DEFAULT_EXTERNAL_REVIEW_SOURCES: dict[str, ExternalReviewSourceConfig] = {
    "company_name": ExternalReviewSourceConfig(sources=["企查查", "国家企业信用信息公示系统", "内部客户库"], suggested_action="建议人工复核主体名称是否为最新版，是否与统一社会信用代码匹配。"),
    "credit_code": ExternalReviewSourceConfig(sources=["企查查", "国家企业信用信息公示系统", "内部数据库"], suggested_action="建议人工复核统一社会信用代码是否与主体名称一致。"),
    "id_number": ExternalReviewSourceConfig(sources=["身份证件", "委托材料", "内部客户库"], suggested_action="建议人工复核身份证号是否与主体身份材料一致。"),
    "phone_number": ExternalReviewSourceConfig(sources=["联系信息表", "委托材料", "内部客户库"], suggested_action="建议人工复核手机号是否与授权材料一致。"),
    "legal_representative": ExternalReviewSourceConfig(sources=["企查查", "国家企业信用信息公示系统", "内部客户库"], suggested_action="建议人工复核法定代表人是否已变更。"),
    "address": ExternalReviewSourceConfig(sources=["企查查", "国家企业信用信息公示系统", "内部客户库", "合同台账"], suggested_action="建议人工复核住所地或联系地址是否为最新版。"),
    "case_number": ExternalReviewSourceConfig(sources=["法院系统", "律所案件台账", "内部数据库"], suggested_action="建议人工复核案号格式和案件信息是否正确。"),
    "court_or_arbitration": ExternalReviewSourceConfig(sources=["法院官网", "仲裁机构官网", "案件台账"], suggested_action="建议人工复核管辖机构名称是否准确。"),
    "institution": ExternalReviewSourceConfig(sources=["法院官网", "仲裁机构官网", "案件台账"], suggested_action="建议人工复核管辖机构名称是否准确。"),
    "contract_number": ExternalReviewSourceConfig(sources=["合同原件", "合同台账", "内部数据库"], suggested_action="建议人工复核合同编号是否与原始合同一致。"),
    "contract_no": ExternalReviewSourceConfig(sources=["合同原件", "合同台账", "内部数据库"], suggested_action="建议人工复核合同编号是否与原始合同一致。"),
    "amount": ExternalReviewSourceConfig(sources=["合同", "对账单", "发票", "财务台账", "客户确认材料"], suggested_action="建议人工复核金额是否与基础材料、诉讼请求和事实部分一致。"),
    "date": ExternalReviewSourceConfig(sources=["合同", "补充协议", "付款记录", "送达记录", "案件台账"], suggested_action="建议人工复核日期是否与基础材料和案件时间线一致。"),
    "evidence_number": ExternalReviewSourceConfig(sources=["证据目录", "附件清单", "案件材料库"], suggested_action="建议人工复核证据编号是否存在，是否与证据目录一致。"),
    "attachment_number": ExternalReviewSourceConfig(sources=["证据目录", "附件清单", "案件材料库"], suggested_action="建议人工复核附件编号是否存在，是否与证据目录一致。"),
    "evidence_no": ExternalReviewSourceConfig(sources=["证据目录", "附件清单", "案件材料库"], suggested_action="建议人工复核证据编号是否存在，是否与证据目录一致。"),
    "placeholder": ExternalReviewSourceConfig(sources=["文书模板", "承办律师确认"], suggested_action="建议人工复核占位符是否应删除、补充或替换为正式内容。"),
    "default": ExternalReviewSourceConfig(sources=["基础材料", "案件台账", "内部数据库"], suggested_action="建议人工复核该字段是否与外部基础材料一致。"),
}


def default_config() -> ReviewRulesConfig:
    now = datetime.now().isoformat(timespec="seconds")
    return ReviewRulesConfig(
        config_version="default-v1",
        updated_at=now,
        enabled_risk_types=sorted(VALID_RISK_TYPES),
        critical_fields=["当事人名称", "法定代表人", "地址", "统一社会信用代码", "案号"],
        placeholder_patterns=["待补充", "X{2,}", "x{2,}", "某某", "202X", "20XX", r"【\s*】", "____+"],
        severity_mapping={
            "PLACEHOLDER_REMAINING": "high",
            "EVIDENCE_REFERENCE_MISSING": "high",
            "AMOUNT_INCONSISTENCY": "high",
            "DATE_LOGIC_WARNING": "medium",
            "POSSIBLY_OUTDATED": "low",
            "SPELLING_VARIATION": "medium",
            "CLAUSE_NUMBERING_ERROR": "medium",
            "CLIENT_PROFILE_MISMATCH": "high",
            "MISSING_STANDARD_CLAUSE": "high",
            "TEMPLATE_FIELD_MISMATCH": "medium",
            "STATUTE_REPEALED": "high",
            "STATUTE_ARTICLE_OUT_OF_RANGE": "high",
            "STATUTE_UNVERIFIED": "low",
        },
        external_review_sources=DEFAULT_EXTERNAL_REVIEW_SOURCES,
        document_profiles=_default_document_profiles(),
        field_dictionary=_default_field_dictionary(),
    )


def load_review_config_with_status(path: str | Path | None = None) -> ReviewRulesConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        config = default_config().model_copy(update={"fallback_used": True, "config_path": str(config_path)})
        return config
    try:
        data = _read_config_file(config_path)
        config = ReviewRulesConfig.model_validate(data)
        return config.model_copy(update={"fallback_used": False, "config_path": str(config_path)})
    except Exception:
        config = default_config().model_copy(update={"fallback_used": True, "config_path": str(config_path)})
        return config


@lru_cache(maxsize=8)
def load_review_config(path: str | Path | None = None) -> ReviewRulesConfig:
    return load_review_config_with_status(path)


def validate_config_data(data: dict[str, Any]) -> ReviewRulesConfig:
    return ReviewRulesConfig.model_validate(data)


def export_config(config: ReviewRulesConfig | None = None) -> str:
    config = config or load_review_config()
    payload = config.model_dump(exclude={"fallback_used", "config_path"}, mode="json")
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def import_config_file(
    source_path: str | Path,
    target_path: str | Path = DEFAULT_CONFIG_PATH,
    backup_dir: str | Path = "data/config_backups",
    change_note: str | None = None,
) -> tuple[ReviewRulesConfig, Path | None]:
    source = Path(source_path)
    target = Path(target_path)
    data = _read_config_file(source)
    config = validate_config_data(data)
    backup_path = backup_config(target, backup_dir) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(exclude={"fallback_used", "config_path"}, mode="json")
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["updated_by"] = payload.get("updated_by") or "local_user"
    payload["change_note"] = change_note
    target.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_review_config.cache_clear()
    return ReviewRulesConfig.model_validate(payload), backup_path


def restore_default_config(
    target_path: str | Path = DEFAULT_CONFIG_PATH,
    backup_dir: str | Path = "data/config_backups",
) -> tuple[ReviewRulesConfig, Path | None]:
    target = Path(target_path)
    backup_path = backup_config(target, backup_dir) if target.exists() else None
    config = default_config()
    target.write_text(export_config(config), encoding="utf-8")
    load_review_config.cache_clear()
    return config, backup_path


def backup_config(config_path: str | Path, backup_dir: str | Path = "data/config_backups") -> Path:
    source = Path(config_path)
    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"review_rules_{timestamp}.yml"
    shutil.copy2(source, backup_path)
    return backup_path


def _read_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("配置文件根节点必须是对象")
    return data


def _validate_regex_patterns(patterns: list[str], label: str) -> None:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{label} contains invalid regex {pattern!r}: {exc}") from exc


def _legacy_rule_key(key: str) -> str:
    mapping = {
        "court_or_arbitration": "institution",
        "contract_number": "contract_no",
        "evidence_number": "evidence_no",
        "attachment_number": "evidence_no",
    }
    return mapping.get(key, key)


def _profile_field_to_extracted(field: str) -> str:
    mapping = {
        "party_name": "当事人名称",
        "case_number": "案号",
        "court_name": "法院 / 仲裁机构名称",
        "amount": "金额",
        "evidence_number": "证据编号",
        "legal_representative": "法定代表人",
        "credit_code": "统一社会信用代码",
        "address": "地址",
        "contract_number": "合同编号",
        "date": "日期",
    }
    return mapping.get(field, field)


def _default_document_profiles() -> dict[str, DocumentProfileConfig]:
    return {
        "general": DocumentProfileConfig(display_name="通用文书", required_fields=["party_name", "case_number", "legal_representative", "credit_code", "address"]),
        "civil_complaint": DocumentProfileConfig(
            display_name="民事起诉状",
            required_fields=["party_name", "case_number", "court_name", "amount", "evidence_number"],
            field_aliases={"party_name": ["原告", "被告", "申请人", "被申请人"], "amount": ["诉讼请求", "欠款金额", "本金", "利息"]},
            amount_keywords=["诉讼请求", "欠款", "本金", "利息"],
            date_keywords=["签署日期", "履行期限", "起诉日期"],
            evidence_keywords=["证据", "附件"],
        ),
        "defense_statement": DocumentProfileConfig(display_name="答辩状", required_fields=["party_name", "case_number", "court_name"]),
        "arbitration_application": DocumentProfileConfig(display_name="仲裁申请书", required_fields=["party_name", "amount", "evidence_number"]),
        "contract_review": DocumentProfileConfig(display_name="合同审查", required_fields=["party_name", "contract_number", "amount", "date"]),
        "lawyer_letter": DocumentProfileConfig(display_name="律师函", required_fields=["party_name", "amount", "date"]),
        "enforcement_application": DocumentProfileConfig(display_name="执行申请书", required_fields=["party_name", "case_number", "amount"]),
    }


def _default_field_dictionary() -> dict[str, FieldConfig]:
    return {
        "party_name": FieldConfig(display_name="主体名称", aliases=["原告", "被告", "申请人", "被申请人", "甲方", "乙方"], suggested_review_sources=["企查查", "国家企业信用信息公示系统"], default_severity="high", required_by_default=True),
        "credit_code": FieldConfig(display_name="统一社会信用代码", aliases=["统一社会信用代码", "信用代码"], regex_patterns=[r"[0-9A-Z]{18}"], suggested_review_sources=["国家企业信用信息公示系统"], default_severity="high", required_by_default=True),
        "id_number": FieldConfig(display_name="身份证号", aliases=["身份证号", "公民身份号码"], regex_patterns=[r"\d{17}[\dXx]"], suggested_review_sources=["身份证件"], default_severity="high"),
        "legal_representative": FieldConfig(display_name="法定代表人", aliases=["法定代表人", "法定代表"], suggested_review_sources=["企查查"], default_severity="high", required_by_default=True),
        "address": FieldConfig(display_name="地址", aliases=["住所地", "地址"], suggested_review_sources=["企查查", "合同台账"], default_severity="medium", required_by_default=True),
        "case_number": FieldConfig(display_name="案号", aliases=["案号"], suggested_review_sources=["法院系统", "案件台账"], default_severity="medium", required_by_default=True),
        "court": FieldConfig(display_name="法院", aliases=["人民法院", "法院"], suggested_review_sources=["法院官网", "案件台账"], default_severity="medium"),
        "arbitration": FieldConfig(display_name="仲裁机构", aliases=["仲裁委员会", "仲裁机构"], suggested_review_sources=["仲裁机构官网"], default_severity="medium"),
        "contract_number": FieldConfig(display_name="合同编号", aliases=["合同编号", "编号"], suggested_review_sources=["合同原件", "合同台账"], default_severity="medium"),
        "amount": FieldConfig(display_name="金额", aliases=["金额", "货款", "本金", "利息"], regex_patterns=[r"(?:人民币)?[0-9][0-9,]*(?:\.\d+)?\s*元"], suggested_review_sources=["合同", "对账单", "发票"], default_severity="high"),
        "date": FieldConfig(display_name="日期", aliases=["日期", "签署日期", "履行期限"], regex_patterns=[r"\d{4}年\d{1,2}月\d{1,2}日"], suggested_review_sources=["合同", "付款记录"], default_severity="medium"),
        "interest_start_date": FieldConfig(display_name="利息起算日", aliases=["利息起算日", "利息自"], suggested_review_sources=["合同", "付款记录"], default_severity="medium"),
        "evidence_number": FieldConfig(display_name="证据编号", aliases=["证据", "证据编号"], suggested_review_sources=["证据目录"], default_severity="high"),
        "attachment_number": FieldConfig(display_name="附件编号", aliases=["附件", "附件编号"], suggested_review_sources=["附件清单"], default_severity="medium"),
    }
