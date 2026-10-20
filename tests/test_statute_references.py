import json

from app.extractors.llm_extractor import extract_structured_entities
from app.extractors.statute_extractor import chinese_numeral_to_int, extract_statute_entities, normalize_statute_citation
from app.llm import client as llm_client
from app.models.schemas import TextChunk
from app.review_engine import review_single_document_result
from app.validators.statute_rules import check_statute_references


class _FakeResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._data


def _chunks(*texts: str) -> list[TextChunk]:
    return [TextChunk(text=text, location=f"段落{index}") for index, text in enumerate(texts, start=1)]


def _normalized_citations(chunks: list[TextChunk]) -> list[str]:
    return [entity.normalized_value for entity in extract_statute_entities(chunks)]


def test_chinese_numerals_convert_to_article_numbers():
    assert chinese_numeral_to_int("五百七十七") == 577
    assert chinese_numeral_to_int("一千二百六十") == 1260
    assert chinese_numeral_to_int("一百零七") == 107
    assert chinese_numeral_to_int("十二") == 12
    assert chinese_numeral_to_int("122") == 122


def test_extracts_bracketed_citation_with_multiple_articles():
    citations = _normalized_citations(_chunks("根据《中华人民共和国民法典》第五百七十七条、第五百七十九条之规定，被告应承担违约责任。"))
    assert citations == ["《民法典》第577条", "《民法典》第579条"]


def test_extracts_unbracketed_and_versioned_citations():
    citations = _normalized_citations(
        _chunks(
            "依据民事诉讼法第一百二十二条第一款提起诉讼。",
            "参照《中华人民共和国民事诉讼法（2023年修正）》第122条。",
            "依照劳动合同法第三十八条主张解除。",
        )
    )
    assert citations == ["《民事诉讼法》第122条", "《民事诉讼法》第122条", "《劳动合同法》第38条"]


def test_contract_clause_references_are_not_statutes():
    assert _normalized_citations(_chunks("被告违反《技术服务合同》第三条的约定。")) == []


def test_normalize_single_citation_value():
    assert normalize_statute_citation("《中华人民共和国合同法》第一百零七条") == "《合同法》第107条"
    assert normalize_statute_citation("第三条") is None


def test_mock_extraction_includes_statute_references():
    extraction = extract_structured_entities(_chunks("根据《民法典》第五百零九条，双方应全面履行义务。"), force_llm=False)
    assert extraction.values("statute_reference") == ["《民法典》第509条"]


def test_llm_statute_references_are_normalized(monkeypatch):
    monkeypatch.setenv("LEGAL_LLM_API_KEY", "test-key")
    payload = {
        "parties": [],
        "company_names": [],
        "credit_codes": [],
        "legal_representatives": [],
        "registered_addresses": [],
        "dates": [],
        "amounts": [],
        "contract_ids": [],
        "statute_references": [{"value": "《中华人民共和国民法典》第五百七十七条"}],
    }

    def fake_urlopen(_request, timeout):
        return _FakeResponse({"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]})

    monkeypatch.setattr(llm_client.request, "urlopen", fake_urlopen)
    extraction = extract_structured_entities(_chunks("根据《中华人民共和国民法典》第五百七十七条主张违约责任。"), force_llm=True)

    assert extraction.mode == "llm"
    assert extraction.values("statute_reference") == ["《民法典》第577条"]


def _risk_types_for(text: str) -> dict[str, str]:
    extraction = extract_structured_entities(_chunks(text), force_llm=False)
    return {finding.risk_type: finding.severity for finding in check_statute_references(extraction)}


def test_repealed_law_is_flagged_high():
    assert _risk_types_for("依据《中华人民共和国合同法》第一百零七条，被告应承担违约责任。") == {"STATUTE_REPEALED": "high"}


def test_article_number_beyond_law_length_is_flagged():
    assert _risk_types_for("依据《民法典》第一千二百八十条主张权利。") == {"STATUTE_ARTICLE_OUT_OF_RANGE": "high"}


def test_unknown_law_is_flagged_for_manual_verification():
    risk_types = _risk_types_for("依据《最高人民法院关于审理买卖合同纠纷案件适用法律问题的解释》第十八条。")
    assert risk_types == {"STATUTE_UNVERIFIED": "low"}


def test_valid_current_citation_produces_no_finding():
    assert _risk_types_for("依据《民法典》第五百七十七条主张违约责任。") == {}


def test_review_pipeline_reports_repealed_statute(monkeypatch):
    monkeypatch.delenv("LEGAL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = review_single_document_result(_chunks("原告：上海星澜智能科技有限公司。", "依据《合同法》第一百零七条，被告应承担违约责任。"))

    statute_findings = [finding for finding in result.findings if finding.risk_type == "STATUTE_REPEALED"]
    assert len(statute_findings) == 1
    assert statute_findings[0].field_name == "法条引用"
    assert statute_findings[0].source_location == "段落2"
    assert "民法典" in (statute_findings[0].reference_value or "")
