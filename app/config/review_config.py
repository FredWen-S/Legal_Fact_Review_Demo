from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


DEFAULT_CONFIG_PATH = Path(__file__).with_name("review_rules.yml")


class ReviewRulesConfig(BaseModel):
    enabled_risk_types: list[str] = Field(default_factory=list)
    critical_fields: list[str] = Field(default_factory=list)
    placeholder_patterns: list[str] = Field(default_factory=list)
    severity_overrides: dict[str, str] = Field(default_factory=dict)
    external_review_sources: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def risk_enabled(self, risk_type: str) -> bool:
        return not self.enabled_risk_types or risk_type in self.enabled_risk_types

    def severity_for(self, risk_type: str, default: str) -> str:
        configured = self.severity_overrides.get(risk_type, default)
        return configured if configured in {"low", "medium", "high"} else default

    def external_review_rule(self, key: str) -> dict[str, Any]:
        return self.external_review_sources.get(key, DEFAULT_EXTERNAL_REVIEW_SOURCES.get(key, DEFAULT_EXTERNAL_REVIEW_SOURCES["default"]))


DEFAULT_EXTERNAL_REVIEW_SOURCES: dict[str, dict[str, Any]] = {
    "company_name": {
        "sources": ["企查查", "国家企业信用信息公示系统", "内部客户库"],
        "suggested_action": "建议人工复核主体名称是否为最新版，是否与统一社会信用代码匹配。",
    },
    "credit_code": {
        "sources": ["企查查", "国家企业信用信息公示系统", "内部数据库"],
        "suggested_action": "建议人工复核统一社会信用代码是否与主体名称一致。",
    },
    "id_number": {
        "sources": ["身份证件", "委托材料", "内部客户库"],
        "suggested_action": "建议人工复核身份证号是否与主体身份材料一致。",
    },
    "legal_representative": {
        "sources": ["企查查", "国家企业信用信息公示系统", "内部客户库"],
        "suggested_action": "建议人工复核法定代表人是否已变更。",
    },
    "address": {
        "sources": ["企查查", "国家企业信用信息公示系统", "内部客户库", "合同台账"],
        "suggested_action": "建议人工复核住所地或联系地址是否为最新版。",
    },
    "case_number": {
        "sources": ["法院系统", "律所案件台账", "内部数据库"],
        "suggested_action": "建议人工复核案号格式和案件信息是否正确。",
    },
    "institution": {
        "sources": ["法院官网", "仲裁机构官网", "案件台账"],
        "suggested_action": "建议人工复核管辖机构名称是否准确。",
    },
    "amount": {
        "sources": ["合同", "对账单", "发票", "财务台账", "客户确认材料"],
        "suggested_action": "建议人工复核金额是否与基础材料、诉讼请求和事实部分一致。",
    },
    "date": {
        "sources": ["合同", "补充协议", "付款记录", "送达记录", "案件台账"],
        "suggested_action": "建议人工复核日期是否与基础材料和案件时间线一致。",
    },
    "evidence_no": {
        "sources": ["证据目录", "附件清单", "案件材料库"],
        "suggested_action": "建议人工复核证据编号是否存在，是否与证据目录一致。",
    },
    "contract_no": {
        "sources": ["合同原件", "合同台账", "内部数据库"],
        "suggested_action": "建议人工复核合同编号是否与原始合同一致。",
    },
    "placeholder": {
        "sources": ["文书模板", "承办律师确认"],
        "suggested_action": "建议人工复核占位符是否应删除、补充或替换为正式内容。",
    },
    "default": {
        "sources": ["基础材料", "案件台账", "内部数据库"],
        "suggested_action": "建议人工复核该字段是否与外部基础材料一致。",
    },
}


@lru_cache(maxsize=4)
def load_review_config(path: str | Path | None = None) -> ReviewRulesConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return ReviewRulesConfig()
    try:
        with config_path.open("r", encoding="utf-8") as file:
            data: dict[str, Any] = yaml.safe_load(file) or {}
        return ReviewRulesConfig.model_validate(data)
    except Exception:
        return ReviewRulesConfig(external_review_sources=DEFAULT_EXTERNAL_REVIEW_SOURCES)
