from __future__ import annotations

import re
from difflib import SequenceMatcher

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.extractors.field_extractor import extract_fields
from app.extractors.statute_extractor import extract_statute_entities, normalize_statute_citation
from app.llm.client import LLMSettings, fallback_reason, load_llm_settings, request_json_completion
from app.models.schemas import ExtractedItem, StructuredEntity, StructuredExtractionResult, TextChunk
from app.utils import normalize_text


ROLE_PATTERN = re.compile(r"^(原告|被告|申请人|被申请人|甲方|乙方)[:：\s]*(.+)")
COMPANY_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9（）()]{4,}(?:公司|集团|事务所|研究院)")
ADDRESS_PATTERN = re.compile(r"(?:注册地址|注册地|住所地|地址)[:：\s]*([^\n。；;]{6,})")
DATE_PATTERN = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")
AMOUNT_PATTERN = re.compile(r"(?:人民币)?[0-9][0-9,]*(?:\.\d+)?\s*元")
CONTRACT_ID_PATTERN = re.compile(r"(?:合同编号|合同号|合同ID|合同id|Contract ID)[:：]?\s*([A-Za-z0-9\-_/.]{4,})")

ENTITY_TO_FIELD_NAME = {
    "party": "当事人名称",
    "company_name": "当事人名称",
    "credit_code": "统一社会信用代码",
    "legal_representative": "法定代表人",
    "registered_address": "地址",
    "date": "日期",
    "amount": "金额",
    "contract_id": "合同编号",
    "statute_reference": "法条引用",
}


class _LLMEntityPayload(BaseModel):
    value: str
    role: str | None = None

    @field_validator("value")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("entity value must not be blank")
        return text

    @field_validator("role")
    @classmethod
    def clean_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class _LLMExtractionPayload(BaseModel):
    parties: list[_LLMEntityPayload]
    company_names: list[_LLMEntityPayload]
    credit_codes: list[_LLMEntityPayload]
    legal_representatives: list[_LLMEntityPayload]
    registered_addresses: list[_LLMEntityPayload]
    dates: list[_LLMEntityPayload]
    amounts: list[_LLMEntityPayload]
    contract_ids: list[_LLMEntityPayload]
    # Optional so responses from prompts without statute support still validate.
    statute_references: list[_LLMEntityPayload] = Field(default_factory=list)


def extract_structured_entities(
    chunks: list[TextChunk],
    force_llm: bool | None = None,
) -> StructuredExtractionResult:
    try:
        settings = load_llm_settings()
    except Exception as exc:
        return _mock_extract_structured_entities(chunks, fallback_reason=fallback_reason("settings_error", exc))

    llm_available = bool(settings.api_key)
    if not llm_available:
        return _mock_extract_structured_entities(chunks, fallback_reason="no_api_key")
    if force_llm is False:
        return _mock_extract_structured_entities(chunks, fallback_reason="llm_disabled")

    use_llm = llm_available if force_llm is None else bool(force_llm)
    if use_llm:
        try:
            return _extract_with_remote_llm(chunks, settings)
        except Exception as exc:
            return _mock_extract_structured_entities(chunks, fallback_reason=fallback_reason("llm_fallback", exc))
    return _mock_extract_structured_entities(chunks, fallback_reason="llm_disabled")


def extract_with_llm(chunks: list[TextChunk], enabled: bool = False) -> list[ExtractedItem]:
    result = extract_structured_entities(chunks, force_llm=enabled)
    return structured_entities_to_extracted_items(result)


def structured_entities_to_extracted_items(result: StructuredExtractionResult) -> list[ExtractedItem]:
    items: list[ExtractedItem] = []
    seen: set[tuple[str, str, str]] = set()
    for entity in result.entities:
        field_name = ENTITY_TO_FIELD_NAME[entity.entity_type]
        key = (field_name, entity.value, entity.source_location)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            ExtractedItem(
                field_name=field_name,
                value=entity.value,
                source_location=entity.source_location,
                confidence=entity.confidence,
                context=entity.context,
            )
        )
    return items


def _mock_extract_structured_entities(
    chunks: list[TextChunk],
    fallback_reason: str | None = None,
) -> StructuredExtractionResult:
    regex_items = extract_fields(chunks)
    entities: list[StructuredEntity] = []
    entities.extend(_extract_party_entities(chunks))
    entities.extend(_entities_from_regex_items(regex_items, "credit_code", {"统一社会信用代码"}))
    entities.extend(_entities_from_regex_items(regex_items, "legal_representative", {"法定代表人"}))
    entities.extend(_entities_from_regex_items(regex_items, "date", {"日期"}))
    entities.extend(_entities_from_regex_items(regex_items, "amount", {"金额"}))
    entities.extend(_entities_from_regex_items(regex_items, "contract_id", {"合同编号"}))
    entities.extend(extract_statute_entities(chunks))

    for chunk in chunks:
        for match in COMPANY_PATTERN.finditer(chunk.text):
            entities.append(
                StructuredEntity(
                    entity_type="company_name",
                    value=match.group(0).strip("，。；; "),
                    normalized_value=match.group(0).strip("，。；; "),
                    source_location=chunk.location,
                    confidence=0.8,
                    context=chunk.text[:300],
                )
            )
        for match in ADDRESS_PATTERN.finditer(chunk.text):
            entities.append(
                StructuredEntity(
                    entity_type="registered_address",
                    value=match.group(1).strip(),
                    normalized_value=match.group(1).strip(),
                    source_location=chunk.location,
                    confidence=0.78,
                    context=chunk.text[:300],
                )
            )
        for match in DATE_PATTERN.finditer(chunk.text):
            entities.append(
                StructuredEntity(
                    entity_type="date",
                    value=match.group(0),
                    normalized_value=match.group(0),
                    source_location=chunk.location,
                    confidence=0.76,
                    context=chunk.text[:300],
                )
            )
        for match in AMOUNT_PATTERN.finditer(chunk.text):
            entities.append(
                StructuredEntity(
                    entity_type="amount",
                    value=match.group(0),
                    normalized_value=_normalize_amount(match.group(0)),
                    source_location=chunk.location,
                    confidence=0.78,
                    context=chunk.text[:300],
                )
            )
        for match in CONTRACT_ID_PATTERN.finditer(chunk.text):
            entities.append(
                StructuredEntity(
                    entity_type="contract_id",
                    value=match.group(1).strip(),
                    normalized_value=match.group(1).strip(),
                    source_location=chunk.location,
                    confidence=0.8,
                    context=chunk.text[:300],
                )
            )

    return StructuredExtractionResult(
        mode="mock",
        model_name="deterministic-mock-extractor",
        entities=_dedupe_entities(entities),
        fallback_reason=fallback_reason,
    )


def _extract_with_remote_llm(chunks: list[TextChunk], settings: LLMSettings) -> StructuredExtractionResult:
    system_prompt = (
        "You extract structured contract and legal-document entities. "
        "Return strict JSON with keys: parties, company_names, credit_codes, "
        "legal_representatives, registered_addresses, dates, amounts, contract_ids, statute_references. "
        "Each list item should be an object with value and optional role. "
        "statute_references lists each cited law article separately, e.g. 《中华人民共和国民法典》第五百七十七条; "
        "do not include references to contract clauses. "
        "Do not add commentary."
    )
    parsed, message = request_json_completion(settings, system_prompt, _build_prompt(chunks))
    try:
        payload = _LLMExtractionPayload.model_validate(parsed)
    except ValidationError as exc:
        raise RuntimeError("llm_schema_validation_failure") from exc

    entities = _entities_from_llm_payload(payload, chunks)
    return StructuredExtractionResult(
        mode="llm",
        model_name=settings.model,
        entities=_dedupe_entities(entities),
        raw_response=message,
    )


def _build_prompt(chunks: list[TextChunk]) -> str:
    rendered = [f"[{chunk.location}] {chunk.text}" for chunk in chunks]
    return (
        "Document text follows.\n"
        "Extract the requested entities using exact spans from the document whenever possible.\n\n"
        + "\n".join(rendered)
    )


def _entities_from_llm_payload(payload: _LLMExtractionPayload, chunks: list[TextChunk]) -> list[StructuredEntity]:
    mapping = {
        "parties": "party",
        "company_names": "company_name",
        "credit_codes": "credit_code",
        "legal_representatives": "legal_representative",
        "registered_addresses": "registered_address",
        "dates": "date",
        "amounts": "amount",
        "contract_ids": "contract_id",
        "statute_references": "statute_reference",
    }
    entities: list[StructuredEntity] = []
    for key, entity_type in mapping.items():
        for item in getattr(payload, key):
            value = item.value.strip()
            role = item.role
            source_location, context = _find_location_for_value(value, chunks)
            entities.append(
                StructuredEntity(
                    entity_type=entity_type,  # type: ignore[arg-type]
                    value=value,
                    normalized_value=_normalized_value(entity_type, value),
                    role=role,
                    source_location=source_location,
                    confidence=0.84,
                    context=context,
                )
            )
    return entities


def _extract_party_entities(chunks: list[TextChunk]) -> list[StructuredEntity]:
    entities: list[StructuredEntity] = []
    for chunk in chunks:
        match = ROLE_PATTERN.search(chunk.text.strip())
        if not match:
            continue
        role, raw_value = match.groups()
        value = re.split(r"[，。；;]", raw_value.strip())[0].strip()
        if not value:
            continue
        entities.append(
            StructuredEntity(
                entity_type="party",
                value=value,
                normalized_value=value,
                role=role,
                source_location=chunk.location,
                confidence=0.88,
                context=chunk.text[:300],
            )
        )
        if "公司" in value or "集团" in value or "事务所" in value:
            entities.append(
                StructuredEntity(
                    entity_type="company_name",
                    value=value,
                    normalized_value=value,
                    role=role,
                    source_location=chunk.location,
                    confidence=0.86,
                    context=chunk.text[:300],
                )
            )
    return entities


def _entities_from_regex_items(
    items: list[ExtractedItem],
    entity_type: str,
    field_names: set[str],
) -> list[StructuredEntity]:
    entities: list[StructuredEntity] = []
    for item in items:
        if item.field_name not in field_names:
            continue
        entities.append(
            StructuredEntity(
                entity_type=entity_type,  # type: ignore[arg-type]
                value=item.value,
                normalized_value=_normalized_value(entity_type, item.value),
                source_location=item.source_location,
                confidence=item.confidence,
                context=item.context,
            )
        )
    return entities


def _normalized_value(entity_type: str, value: str) -> str:
    if entity_type == "amount":
        return _normalize_amount(value)
    if entity_type == "statute_reference":
        return normalize_statute_citation(value) or value.strip()
    return value.strip()


def _normalize_amount(value: str) -> str:
    digits = re.sub(r"[^\d.]", "", value)
    return digits or value.strip()


def _find_location_for_value(value: str, chunks: list[TextChunk]) -> tuple[str, str | None]:
    normalized = normalize_text(value)
    best_chunk = chunks[0] if chunks else TextChunk(text="", location="全文")
    best_score = -1.0
    for chunk in chunks:
        chunk_norm = normalize_text(chunk.text)
        if normalized and normalized in chunk_norm:
            return chunk.location, chunk.text[:300]
        score = SequenceMatcher(None, normalized, chunk_norm[: max(len(normalized), 1) * 4]).ratio()
        if score > best_score:
            best_chunk = chunk
            best_score = score
    return best_chunk.location, best_chunk.text[:300] if best_chunk.text else None


def _dedupe_entities(entities: list[StructuredEntity]) -> list[StructuredEntity]:
    seen: set[tuple[str, str, str, str | None]] = set()
    deduped: list[StructuredEntity] = []
    for entity in entities:
        key = (entity.entity_type, entity.value, entity.source_location, entity.role)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
    return deduped
