from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError, field_validator

from app.llm.client import LLMSettings, fallback_reason, load_llm_settings, request_json_completion
from app.models.schemas import FORBIDDEN_REVIEW_TERMS, ReviewFinding, RiskExplanationResult, TextChunk


PROMPT_VERSION = "legal-review-risk-explanation-v1"
MAX_LLM_FINDINGS = 30
MAX_EXPLANATION_LENGTH = 300
FORBIDDEN_EXPLANATION_TERMS = FORBIDDEN_REVIEW_TERMS | {"系统已确认", "确认错误", "法律上无效"}

SYSTEM_PROMPT = (
    "你是律师文书复核助手。输入是规则引擎发现的复核项列表。"
    "请针对每一项用中文写一段不超过120字的风险说明：解释该问题为什么值得关注、可能造成什么影响。"
    "只能依据输入中提供的信息，不得编造事实；不得给出确定的法律结论（例如“系统确认错误”“法律上必然无效”），"
    "措辞应为提示律师人工复核。"
    '返回严格 JSON：{"explanations": [{"risk_id": "...", "explanation": "..."}]}，risk_id 必须与输入一致，不要输出其他内容。'
)

_IMPACT_BY_RISK_TYPE = {
    "MISSING_FIELD": "缺少该字段可能导致主体或案件信息不完整，影响文书送达和后续程序。",
    "INTERNAL_CONFLICT": "文书内同一字段出现不一致的表述，可能引发对主体或事实认定的歧义。",
    "SOURCE_MISMATCH": "文书内容与基础信息表不一致，可能是录入错误或基础信息已过期。",
    "FORMAT_ERROR": "格式不规范可能影响文书的严谨性，或导致金额、日期等关键信息被误读。",
    "POSSIBLY_OUTDATED": "参考资料可能已过期，所依据的信息未必反映当前状态。",
    "PLACEHOLDER_REMAINING": "文书中仍保留占位内容，直接提交可能造成信息缺失。",
    "EVIDENCE_REFERENCE_MISSING": "文书引用的证据未在证据目录中找到对应项，可能影响举证的完整性。",
    "AMOUNT_INCONSISTENCY": "金额前后不一致可能使诉讼请求或合同对价不明确，影响主张的确定性。",
    "DATE_LOGIC_WARNING": "日期先后关系异常可能影响履行期限、起算时间或时效的判断。",
    "SPELLING_VARIATION": "主体名称存在近似写法，可能被理解为指向不同主体，影响当事人身份的确定。",
    "CLAUSE_NUMBERING_ERROR": "条款编号不连续或重复，可能导致条款引用错位。",
    "CLIENT_PROFILE_MISMATCH": "文书信息与检索到的客户档案不一致，可能存在主体信息录入错误或档案未更新。",
    "MISSING_STANDARD_CLAUSE": "匹配到的模板要求包含该标准条款，缺失可能导致相关权利义务约定不完整。",
    "TEMPLATE_FIELD_MISMATCH": "字段与模板或客户档案的惯用格式不一致，可能套用了其他模板。",
    "STATUTE_REPEALED": "引用已废止的法律可能削弱主张的法律依据，通常需要改引现行有效的对应条文。",
    "STATUTE_ARTICLE_OUT_OF_RANGE": "条文序号超出该法律的条文总数，引用可能存在笔误或指向了其他法律。",
    "STATUTE_UNVERIFIED": "该法律文件不在本地参考列表中，无法自动核对其效力状态和条文范围。",
}


class _ExplanationItem(BaseModel):
    risk_id: str
    explanation: str

    @field_validator("explanation")
    @classmethod
    def explanation_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("explanation must not be blank")
        return text


class _ExplanationPayload(BaseModel):
    explanations: list[_ExplanationItem]


def explain_findings(
    findings: list[ReviewFinding],
    chunks: list[TextChunk],
    force_llm: bool | None = None,
) -> tuple[list[ReviewFinding], RiskExplanationResult]:
    """Attach a risk explanation to every finding.

    Uses the configured LLM when an API key is available and falls back to
    deterministic template explanations otherwise, recording the reason.
    """
    try:
        settings = load_llm_settings()
    except Exception as exc:
        return _mock_explain(findings, fallback_reason("settings_error", exc))

    if not settings.api_key:
        return _mock_explain(findings, "no_api_key")
    if force_llm is False:
        return _mock_explain(findings, "llm_disabled")
    if not findings:
        return [], RiskExplanationResult(mode="llm", model_name=settings.model, prompt_version=PROMPT_VERSION)

    try:
        return _explain_with_llm(findings, chunks, settings)
    except Exception as exc:
        return _mock_explain(findings, fallback_reason("llm_fallback", exc))


def template_explanation(finding: ReviewFinding) -> str:
    impact = _IMPACT_BY_RISK_TYPE.get(finding.risk_type, "该问题可能影响文书的准确性。")
    return f"{finding.source_location}的「{finding.field_name}」：{impact}建议人工复核后再定稿。"


def _explain_with_llm(
    findings: list[ReviewFinding],
    chunks: list[TextChunk],
    settings: LLMSettings,
) -> tuple[list[ReviewFinding], RiskExplanationResult]:
    batch = findings[:MAX_LLM_FINDINGS]
    parsed, _raw = request_json_completion(settings, SYSTEM_PROMPT, _build_prompt(batch, chunks))
    try:
        payload = _ExplanationPayload.model_validate(parsed)
    except ValidationError as exc:
        raise RuntimeError("risk_explanation_schema_validation_failure") from exc

    requested_ids = {finding.risk_id for finding in batch}
    llm_texts = {
        item.risk_id: item.explanation[:MAX_EXPLANATION_LENGTH]
        for item in payload.explanations
        if item.risk_id in requested_ids and not _contains_forbidden_terms(item.explanation)
    }
    if not llm_texts:
        raise RuntimeError("risk_explanation_empty_or_unsafe")

    explained = [
        _with_explanation(finding, llm_texts[finding.risk_id], "llm")
        if finding.risk_id in llm_texts
        else _with_explanation(finding, template_explanation(finding), "mock")
        for finding in findings
    ]
    return explained, RiskExplanationResult(
        mode="llm",
        model_name=settings.model,
        prompt_version=PROMPT_VERSION,
        explained_count=len(explained),
        llm_explained_count=len(llm_texts),
    )


def _mock_explain(findings: list[ReviewFinding], reason: str) -> tuple[list[ReviewFinding], RiskExplanationResult]:
    explained = [_with_explanation(finding, template_explanation(finding), "mock") for finding in findings]
    return explained, RiskExplanationResult(
        mode="mock",
        model_name="deterministic-template-explainer",
        prompt_version=PROMPT_VERSION,
        explained_count=len(explained),
        fallback_reason=reason,
    )


def _build_prompt(findings: list[ReviewFinding], chunks: list[TextChunk]) -> str:
    context_by_location = {chunk.location: chunk.text[:200] for chunk in chunks}
    items = [
        {
            "risk_id": finding.risk_id,
            "risk_type": finding.risk_type,
            "severity": finding.severity,
            "field_name": finding.field_name,
            "document_value": finding.document_value,
            "reference_value": finding.reference_value,
            "source_location": finding.source_location,
            "rule_reason": finding.reason,
            "document_context": context_by_location.get(finding.source_location),
        }
        for finding in findings
    ]
    return "复核项列表：\n" + json.dumps(items, ensure_ascii=False, indent=2)


def _with_explanation(finding: ReviewFinding, text: str, source: str) -> ReviewFinding:
    return finding.model_copy(update={"risk_explanation": text, "explanation_source": source})


def _contains_forbidden_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in FORBIDDEN_EXPLANATION_TERMS)
