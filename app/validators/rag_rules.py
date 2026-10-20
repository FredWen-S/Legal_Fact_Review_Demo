from __future__ import annotations

from difflib import SequenceMatcher

from app.models.schemas import KnowledgeContext, ReviewFinding, StructuredExtractionResult, TextChunk
from app.utils import normalize_text, stable_id


def check_knowledge_alignment(
    chunks: list[TextChunk],
    structured_extraction: StructuredExtractionResult | None,
    knowledge_context: KnowledgeContext | None,
) -> list[ReviewFinding]:
    if structured_extraction is None or knowledge_context is None:
        return []

    findings: list[ReviewFinding] = []
    document_text = "\n".join(chunk.text for chunk in chunks)
    document_text_normalized = normalize_text(document_text).lower()

    client = knowledge_context.client_profile
    if client is not None and client.match_status != "matched":
        client = None
    if client is not None:
        findings.extend(
            _compare_client_value(
                structured_extraction,
                entity_type="company_name",
                reference_value=str(client.metadata.get("legal_name", "")),
                field_name="当事人名称",
                issue_type="CLIENT_PROFILE_MISMATCH",
                severity="high",
                reference_source=client.path,
            )
        )
        findings.extend(
            _compare_client_value(
                structured_extraction,
                entity_type="credit_code",
                reference_value=str(client.metadata.get("credit_code", "")),
                field_name="统一社会信用代码",
                issue_type="CLIENT_PROFILE_MISMATCH",
                severity="high",
                reference_source=client.path,
            )
        )
        findings.extend(
            _compare_client_value(
                structured_extraction,
                entity_type="legal_representative",
                reference_value=str(client.metadata.get("legal_representative", "")),
                field_name="法定代表人",
                issue_type="CLIENT_PROFILE_MISMATCH",
                severity="medium",
                reference_source=client.path,
            )
        )
        findings.extend(
            _compare_client_value(
                structured_extraction,
                entity_type="registered_address",
                reference_value=str(client.metadata.get("registered_address", "")),
                field_name="注册地址",
                issue_type="CLIENT_PROFILE_MISMATCH",
                severity="medium",
                reference_source=client.path,
            )
        )

        expected_prefixes = [str(item) for item in client.metadata.get("preferred_contract_prefixes", [])]
        contract_ids = structured_extraction.values("contract_id")
        if expected_prefixes and contract_ids and not any(
            contract_id.startswith(prefix) for contract_id in contract_ids for prefix in expected_prefixes
        ):
            location = _first_location(structured_extraction, "contract_id")
            findings.append(
                ReviewFinding(
                    risk_id=stable_id("contract-prefix", *contract_ids, *expected_prefixes),
                    risk_type="TEMPLATE_FIELD_MISMATCH",
                    severity="medium",
                    field_name="合同编号",
                    document_value=" / ".join(contract_ids),
                    reference_value=", ".join(expected_prefixes),
                    source_location=location,
                    reference_source=client.path,
                    confidence=0.79,
                    reason="Extracted contract IDs do not match the preferred client contract prefix in the synthetic client profile.",
                    suggested_action="建议人工复核合同编号是否应与检索到的客户档案前缀一致，或确认该文书是否本就使用了其他模板。",
                )
            )

    matched_templates = [template for template in knowledge_context.templates if template.match_status == "matched"]
    matched_clauses = [clause for clause in knowledge_context.clauses if clause.match_status == "matched"]
    # Only the best-matching template reflects the document type; lower-ranked templates
    # (e.g. a service contract for a complaint) must not impose their required clauses.
    top_template = max(matched_templates, key=lambda template: template.score, default=None)
    required_clause_ids = set(top_template.metadata.get("required_clause_ids", [])) if top_template else set()
    for clause in matched_clauses:
        if clause.doc_id not in required_clause_ids:
            continue
        keywords = clause.metadata.get("presence_keywords") or clause.metadata.get("keywords") or [clause.title]
        normalized_keywords = [normalize_text(str(keyword)).lower() for keyword in keywords if str(keyword).strip()]
        if normalized_keywords and any(keyword in document_text_normalized for keyword in normalized_keywords):
            continue
        findings.append(
            ReviewFinding(
                risk_id=stable_id("missing-clause", clause.doc_id),
                risk_type="MISSING_STANDARD_CLAUSE",
                severity="high",
                field_name="标准条款",
                document_value=clause.title,
                reference_value=clause.metadata.get("summary") or clause.snippet,
                source_location="全文检索",
                reference_source=clause.path,
                confidence=0.76,
                reason="The retrieved knowledge base suggests a relevant standard clause that was not clearly found in the document text.",
                suggested_action="建议人工复核是否需要补充该标准条款，或确认现有表述是否已经覆盖同等要求。",
            )
        )
    return _dedupe_findings(findings)


def _compare_client_value(
    extraction: StructuredExtractionResult,
    entity_type: str,
    reference_value: str,
    field_name: str,
    issue_type: str,
    severity: str,
    reference_source: str,
) -> list[ReviewFinding]:
    if not reference_value.strip():
        return []

    values = extraction.values(entity_type)  # type: ignore[arg-type]
    if not values:
        return []

    reference_norm = normalize_text(reference_value)
    exact_match = any(normalize_text(value) == reference_norm for value in values)
    if exact_match:
        return []

    best_value = max(values, key=lambda value: SequenceMatcher(None, normalize_text(value), reference_norm).ratio())
    best_ratio = SequenceMatcher(None, normalize_text(best_value), reference_norm).ratio()
    location = _location_for_value(extraction, entity_type, best_value)

    if best_ratio >= 0.84 and field_name == "当事人名称":
        return [
            ReviewFinding(
                risk_id=stable_id("client-spelling", best_value, reference_value),
                risk_type="SPELLING_VARIATION",
                severity="medium",
                field_name=field_name,
                document_value=best_value,
                reference_value=reference_value,
                source_location=location,
                reference_source=reference_source,
                confidence=0.82,
                reason="The extracted company name is very close to the retrieved client profile but not identical, suggesting a possible spelling variation.",
                suggested_action="建议人工复核检索到的客户正式名称，并统一文书中的公司名称表述。",
            )
        ]

    return [
        ReviewFinding(
            risk_id=stable_id("client-mismatch", entity_type, best_value, reference_value),
            risk_type=issue_type,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            field_name=field_name,
            document_value=best_value,
            reference_value=reference_value,
            source_location=location,
            reference_source=reference_source,
            confidence=0.85,
            reason="The extracted value does not match the most relevant retrieved synthetic client profile.",
            suggested_action="建议人工复核该字段是否应与检索到的客户档案保持一致，或确认本次文书应关联其他合成客户档案。",
        )
    ]


def _first_location(extraction: StructuredExtractionResult, entity_type: str) -> str:
    for entity in extraction.entities:
        if entity.entity_type == entity_type:
            return entity.source_location
    return "全文检索"


def _location_for_value(extraction: StructuredExtractionResult, entity_type: str, value: str) -> str:
    for entity in extraction.entities:
        if entity.entity_type == entity_type and entity.value == value:
            return entity.source_location
    return _first_location(extraction, entity_type)


def _dedupe_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    seen: set[str] = set()
    deduped: list[ReviewFinding] = []
    for finding in findings:
        key = f"{finding.risk_type}|{finding.field_name}|{finding.document_value}|{finding.reference_value}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped
