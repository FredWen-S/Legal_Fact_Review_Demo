from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.rag.embeddings import (
    EmbeddingComputationError,
    EmbeddingModelLoadError,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    get_embedding_provider,
    load_retrieval_settings,
)
from app.models.schemas import (
    KnowledgeContext,
    KnowledgeMatch,
    KnowledgeRetrievalStatus,
    StructuredExtractionResult,
    TextChunk,
)
from app.utils import normalize_text


KB_ROOT = Path(__file__).resolve().parents[2] / "kb"
DEFAULT_MIN_SCORES = {
    "client": 3.0,
    "template": 0.5,
    "clause": 0.5,
}
DEFAULT_EMBEDDING_MIN_SCORES = {
    "client": 0.6,
    "template": 0.45,
    "clause": 0.45,
}


@dataclass(frozen=True)
class _KnowledgeDocument:
    kb_type: str
    doc_id: str
    title: str
    path: Path
    text: str
    metadata: dict
    tokens: set[str]


@dataclass(frozen=True)
class _DocumentBundle:
    documents: tuple[_KnowledgeDocument, ...]
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _MatchResult:
    matches: list[KnowledgeMatch]
    status: KnowledgeRetrievalStatus


def build_knowledge_context(
    chunks: list[TextChunk],
    extraction: StructuredExtractionResult | None,
    kb_root: Path | None = None,
    min_scores: dict[str, float] | None = None,
    retrieval_backend: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> KnowledgeContext:
    root = kb_root or KB_ROOT
    settings = load_retrieval_settings()
    backend = (retrieval_backend or settings.backend or "lexical").strip().lower()
    query_text = _build_query_text(chunks, extraction)
    query_tokens = _tokenize(query_text)

    if backend == "embedding":
        embedding_thresholds = _thresholds(DEFAULT_EMBEDDING_MIN_SCORES, min_scores, settings.min_score)
        try:
            provider = embedding_provider or get_embedding_provider(settings)
            return _build_embedding_context(root, query_text, query_tokens, extraction, embedding_thresholds, provider)
        except EmbeddingUnavailableError as exc:
            return _fallback_to_lexical_context(root, query_text, query_tokens, extraction, min_scores, "embedding_unavailable_fallback_lexical", exc)
        except EmbeddingModelLoadError as exc:
            return _fallback_to_lexical_context(root, query_text, query_tokens, extraction, min_scores, "embedding_model_load_failed_fallback_lexical", exc)
        except EmbeddingComputationError as exc:
            return _fallback_to_lexical_context(root, query_text, query_tokens, extraction, min_scores, "embedding_computation_failed_fallback_lexical", exc)
        except Exception as exc:
            return _fallback_to_lexical_context(root, query_text, query_tokens, extraction, min_scores, "embedding_failed_fallback_lexical", exc)

    thresholds = _thresholds(DEFAULT_MIN_SCORES, min_scores, settings.min_score)
    return _build_lexical_context(root, query_text, query_tokens, extraction, thresholds)


def _build_lexical_context(
    root: Path,
    query_text: str,
    query_tokens: set[str],
    extraction: StructuredExtractionResult | None,
    thresholds: dict[str, float],
) -> KnowledgeContext:
    client_result = _top_client_match(root, query_text, query_tokens, extraction, thresholds["client"])
    template_result = _top_matches("template", root, query_text, query_tokens, extraction, limit=2, min_score=thresholds["template"])
    clause_result = _top_matches("clause", root, query_text, query_tokens, extraction, limit=3, min_score=thresholds["clause"])
    clause_matches = _merge_template_clauses(root, clause_result.matches, template_result.matches, thresholds["clause"])
    clause_status = _status_from_matches(
        "clause",
        clause_matches,
        clause_result.status,
        thresholds["clause"],
        "Matched standard clauses directly or through a matched template.",
    )

    return KnowledgeContext(
        client_profile=client_result.matches[0] if client_result.matches else None,
        clauses=clause_matches,
        templates=template_result.matches,
        retrieval_statuses=[client_result.status, template_result.status, clause_status],
    )


def _build_query_text(chunks: list[TextChunk], extraction: StructuredExtractionResult | None) -> str:
    parts = [chunk.text for chunk in chunks]
    if extraction is not None:
        for entity in extraction.entities:
            parts.append(entity.value)
            if entity.normalized_value and entity.normalized_value != entity.value:
                parts.append(entity.normalized_value)
            if entity.role:
                parts.append(entity.role)
    return "\n".join(parts)


def _top_client_match(
    kb_root: Path,
    query_text: str,
    query_tokens: set[str],
    extraction: StructuredExtractionResult | None,
    min_score: float,
) -> _MatchResult:
    bundle = _load_document_bundle("client", kb_root)
    if not bundle.documents:
        return _empty_result("client", min_score, _no_documents_reason("client", kb_root, bundle.errors))

    exact_terms: list[tuple[str, float]] = []
    if extraction is not None:
        for value in extraction.values("company_name"):
            exact_terms.append((value, 8.0))
        for value in extraction.values("credit_code"):
            exact_terms.append((value, 12.0))
        for value in extraction.values("legal_representative"):
            exact_terms.append((value, 4.0))
        for value in extraction.values("contract_id"):
            exact_terms.append((value, 2.0))

    scored = [
        (_score_document(document, query_text, query_tokens, exact_terms), document)
        for document in bundle.documents
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_document = scored[0]
    if best_score < min_score:
        return _low_confidence_result("client", best_score, best_document, min_score)
    return _MatchResult(
        matches=[
            _to_match(
                best_document,
                best_score,
                min_score,
                _match_reason(best_score, min_score, exact_terms, best_document, query_tokens),
            )
        ],
        status=KnowledgeRetrievalStatus(
            kb_type="client",
            status="matched",
            min_score=min_score,
            best_score=best_score,
            best_doc_id=best_document.doc_id,
            match_reason=f"Best client profile score {best_score} met minimum {min_score}.",
        ),
    )


def _top_matches(
    kb_type: str,
    kb_root: Path,
    query_text: str,
    query_tokens: set[str],
    extraction: StructuredExtractionResult | None,
    limit: int,
    min_score: float,
) -> _MatchResult:
    bundle = _load_document_bundle(kb_type, kb_root)
    if not bundle.documents:
        return _empty_result(kb_type, min_score, _no_documents_reason(kb_type, kb_root, bundle.errors))

    exact_terms: list[tuple[str, float]] = []
    if extraction is not None:
        exact_terms.extend((value, 3.0) for value in extraction.values("company_name"))
        exact_terms.extend((value, 2.0) for value in extraction.values("contract_id"))

    scored = [
        (_score_document(document, query_text, query_tokens, exact_terms), document)
        for document in bundle.documents
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_document = scored[0]
    eligible = [item for item in scored if item[0] >= min_score]
    if not eligible:
        if best_score > 0:
            return _low_confidence_result(kb_type, best_score, best_document, min_score)
        return _empty_result(kb_type, min_score, f"No {kb_type} document reached a positive score.")
    matches = [
        _to_match(
            document,
            score,
            min_score,
            _match_reason(score, min_score, exact_terms, document, query_tokens),
        )
        for score, document in eligible[:limit]
    ]
    return _MatchResult(
        matches=matches,
        status=KnowledgeRetrievalStatus(
            kb_type=kb_type,  # type: ignore[arg-type]
            status="matched",
            min_score=min_score,
            best_score=best_score,
            best_doc_id=best_document.doc_id,
            match_reason=f"{len(matches)} {kb_type} match(es) met minimum score {min_score}.",
        ),
    )


def _build_embedding_context(
    root: Path,
    query_text: str,
    query_tokens: set[str],
    extraction: StructuredExtractionResult | None,
    thresholds: dict[str, float],
    provider: EmbeddingProvider,
) -> KnowledgeContext:
    client_result = _embedding_matches("client", root, query_text, query_tokens, extraction, limit=1, min_score=thresholds["client"], provider=provider)
    template_result = _embedding_matches("template", root, query_text, query_tokens, extraction, limit=2, min_score=thresholds["template"], provider=provider)
    clause_result = _embedding_matches("clause", root, query_text, query_tokens, extraction, limit=3, min_score=thresholds["clause"], provider=provider)
    clause_matches = _merge_template_clauses(root, clause_result.matches, template_result.matches, thresholds["clause"])
    clause_status = _status_from_matches(
        "clause",
        clause_matches,
        clause_result.status,
        thresholds["clause"],
        "Matched standard clauses using embedding retrieval directly or through a matched template.",
    )

    return KnowledgeContext(
        client_profile=client_result.matches[0] if client_result.matches else None,
        clauses=clause_matches,
        templates=template_result.matches,
        retrieval_statuses=[client_result.status, template_result.status, clause_status],
    )


def _embedding_matches(
    kb_type: str,
    kb_root: Path,
    query_text: str,
    query_tokens: set[str],
    extraction: StructuredExtractionResult | None,
    limit: int,
    min_score: float,
    provider: EmbeddingProvider,
) -> _MatchResult:
    bundle = _load_document_bundle(kb_type, kb_root)
    if not bundle.documents:
        return _empty_result(kb_type, min_score, _no_documents_reason(kb_type, kb_root, bundle.errors))

    try:
        vectors = provider.embed_texts([query_text] + [document.text for document in bundle.documents])
    except EmbeddingComputationError:
        raise
    except Exception as exc:
        raise EmbeddingComputationError("embedding provider failed") from exc
    if len(vectors) != len(bundle.documents) + 1:
        raise EmbeddingComputationError("embedding provider returned an unexpected vector count")

    query_vector = vectors[0]
    exact_terms = _exact_terms_for(kb_type, extraction)
    scored = [
        (_score_embedding(query_vector, vector, document, exact_terms), document)
        for vector, document in zip(vectors[1:], bundle.documents)
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_document = scored[0]
    eligible = [item for item in scored if item[0] >= min_score]
    if not eligible:
        if best_score > 0:
            result = _low_confidence_result(kb_type, best_score, best_document, min_score)
            return _MatchResult(
                matches=[],
                status=result.status.model_copy(
                    update={
                        "match_reason": f"Best {kb_type} embedding candidate '{best_document.title}' scored {best_score}, below minimum {min_score}."
                    }
                ),
            )
        return _empty_result(kb_type, min_score, f"No {kb_type} document reached a positive embedding score.")

    matches = [
        _to_match(
            document,
            score,
            min_score,
            _embedding_match_reason(score, min_score, query_vector, document, exact_terms, query_tokens),
        )
        for score, document in eligible[:limit]
    ]
    return _MatchResult(
        matches=matches,
        status=KnowledgeRetrievalStatus(
            kb_type=kb_type,  # type: ignore[arg-type]
            status="matched",
            min_score=min_score,
            best_score=best_score,
            best_doc_id=best_document.doc_id,
            match_reason=f"{len(matches)} {kb_type} embedding match(es) met minimum score {min_score}.",
        ),
    )


def _merge_template_clauses(
    kb_root: Path,
    clause_matches: list[KnowledgeMatch],
    template_matches: list[KnowledgeMatch],
    min_score: float,
) -> list[KnowledgeMatch]:
    by_id = {match.doc_id: match for match in clause_matches}
    for template in template_matches:
        for clause_id in template.metadata.get("required_clause_ids", []):
            clause_document = _get_document_by_id("clause", clause_id, kb_root)
            if clause_document is None:
                continue
            existing = by_id.get(clause_id)
            if existing is None:
                by_id[clause_id] = _to_match(
                    clause_document,
                    max(template.score - 0.5, min_score),
                    min_score,
                    f"Included because matched template '{template.title}' requires this clause.",
                )
            else:
                boosted = existing.model_copy(
                    update={
                        "score": max(existing.score, template.score),
                        "match_reason": f"{existing.match_reason} Also required by matched template '{template.title}'.",
                    }
                )
                by_id[clause_id] = boosted
    merged = list(by_id.values())
    merged.sort(key=lambda item: item.score, reverse=True)
    return merged[:5]


def _score_document(
    document: _KnowledgeDocument,
    query_text: str,
    query_tokens: set[str],
    exact_terms: Iterable[tuple[str, float]],
) -> float:
    exact_terms = list(exact_terms)
    if not query_tokens and not exact_terms:
        return 0.0

    overlap = len(query_tokens & document.tokens)
    document_norm = normalize_text(document.text).lower()
    phrase_bonus = 0.0
    for term, weight in exact_terms:
        normalized = normalize_text(term).lower()
        if normalized and normalized in document_norm:
            phrase_bonus += weight

    coverage = overlap / math.sqrt(max(len(document.tokens), 1))
    title_bonus = 1.0 if normalize_text(document.title).lower() in normalize_text(query_text).lower() else 0.0
    return round(coverage + phrase_bonus + title_bonus, 4)


def _score_embedding(
    query_vector: list[float],
    document_vector: list[float],
    document: _KnowledgeDocument,
    exact_terms: Iterable[tuple[str, float]],
) -> float:
    exact_terms = list(exact_terms)
    score = _cosine_similarity(query_vector, document_vector)
    document_norm = normalize_text(document.text).lower()
    exact_bonus = 0.0
    for term, weight in exact_terms:
        normalized = normalize_text(term).lower()
        if normalized and normalized in document_norm:
            exact_bonus += min(weight / 100.0, 0.12)
    return round(min(score + exact_bonus, 1.0), 4)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        raise EmbeddingComputationError("embedding vectors must be non-empty and have equal dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(min(dot / (left_norm * right_norm), 1.0), -1.0)


def _to_match(document: _KnowledgeDocument, score: float, min_score: float, match_reason: str) -> KnowledgeMatch:
    body = document.metadata.get("body") or document.metadata.get("summary") or document.text
    snippet = str(body).strip().replace("\n", " ")
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    return KnowledgeMatch(
        kb_type=document.kb_type,  # type: ignore[arg-type]
        doc_id=document.doc_id,
        title=document.title,
        score=score,
        path=str(document.path),
        snippet=snippet,
        metadata=document.metadata,
        match_status="matched",
        match_reason=match_reason,
        min_score=min_score,
    )


def _thresholds(
    defaults: dict[str, float],
    overrides: dict[str, float] | None,
    global_min_score: float | None,
) -> dict[str, float]:
    thresholds = dict(defaults)
    if global_min_score is not None:
        thresholds = {key: global_min_score for key in thresholds}
    thresholds.update(overrides or {})
    return thresholds


@lru_cache(maxsize=32)
def _load_document_bundle(kb_type: str, kb_root: Path) -> _DocumentBundle:
    directory = kb_root / f"{kb_type}s"
    if not directory.exists():
        return _DocumentBundle(documents=(), errors=(f"KB directory not found: {directory}",))

    documents: list[_KnowledgeDocument] = []
    errors: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            errors.append(f"Cannot read KB file {path.name}: {exc}")
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in KB file {path.name}: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"KB file {path.name} must contain a JSON object.")
            continue
        doc_id = str(payload.get("id") or path.stem)
        title = str(payload.get("title") or payload.get("legal_name") or doc_id)
        text_parts: list[str] = [title]
        for key, value in payload.items():
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, list):
                text_parts.extend(str(item) for item in value)
            elif isinstance(value, dict):
                text_parts.extend(f"{inner_key}:{inner_value}" for inner_key, inner_value in value.items())
        text = "\n".join(part for part in text_parts if part)
        documents.append(
            _KnowledgeDocument(
                kb_type=kb_type,
                doc_id=doc_id,
                title=title,
                path=path,
                text=text,
                metadata=payload,
                tokens=_tokenize(text),
            )
        )
    return _DocumentBundle(documents=tuple(documents), errors=tuple(errors))


def _load_documents(kb_type: str, kb_root: Path) -> tuple[_KnowledgeDocument, ...]:
    return _load_document_bundle(kb_type, kb_root).documents


def _get_document_by_id(kb_type: str, doc_id: str, kb_root: Path) -> _KnowledgeDocument | None:
    for document in _load_documents(kb_type, kb_root):
        if document.doc_id == doc_id:
            return document
    return None


def _empty_result(kb_type: str, min_score: float, reason: str) -> _MatchResult:
    return _MatchResult(
        matches=[],
        status=KnowledgeRetrievalStatus(
            kb_type=kb_type,  # type: ignore[arg-type]
            status="no_match",
            min_score=min_score,
            match_reason=reason,
        ),
    )


def _low_confidence_result(
    kb_type: str,
    best_score: float,
    document: _KnowledgeDocument,
    min_score: float,
) -> _MatchResult:
    return _MatchResult(
        matches=[],
        status=KnowledgeRetrievalStatus(
            kb_type=kb_type,  # type: ignore[arg-type]
            status="low_confidence_match",
            min_score=min_score,
            best_score=best_score,
            best_doc_id=document.doc_id,
            match_reason=f"Best {kb_type} candidate '{document.title}' scored {best_score}, below minimum {min_score}.",
        ),
    )


def _status_from_matches(
    kb_type: str,
    matches: list[KnowledgeMatch],
    fallback_status: KnowledgeRetrievalStatus,
    min_score: float,
    reason: str,
) -> KnowledgeRetrievalStatus:
    if matches:
        best = max(matches, key=lambda item: item.score)
        return KnowledgeRetrievalStatus(
            kb_type=kb_type,  # type: ignore[arg-type]
            status="matched",
            min_score=min_score,
            best_score=best.score,
            best_doc_id=best.doc_id,
            match_reason=reason,
        )
    return fallback_status


def _no_documents_reason(kb_type: str, kb_root: Path, errors: tuple[str, ...]) -> str:
    if errors:
        return "; ".join(errors)
    return f"No {kb_type} KB documents were found under {kb_root}."


def _fallback_to_lexical_context(
    root: Path,
    query_text: str,
    query_tokens: set[str],
    extraction: StructuredExtractionResult | None,
    min_scores: dict[str, float] | None,
    fallback_code: str,
    exc: Exception,
) -> KnowledgeContext:
    context = _build_lexical_context(root, query_text, query_tokens, extraction, _thresholds(DEFAULT_MIN_SCORES, min_scores, None))
    reason = f"{fallback_code}: {str(exc) or exc.__class__.__name__}"
    return _annotate_fallback_context(context, reason)


def _annotate_fallback_context(context: KnowledgeContext, reason: str) -> KnowledgeContext:
    def annotate_match(match: KnowledgeMatch) -> KnowledgeMatch:
        return match.model_copy(update={"match_reason": f"{reason}; {match.match_reason}"})

    return context.model_copy(
        update={
            "client_profile": annotate_match(context.client_profile) if context.client_profile else None,
            "templates": [annotate_match(match) for match in context.templates],
            "clauses": [annotate_match(match) for match in context.clauses],
            "retrieval_statuses": [
                status.model_copy(update={"match_reason": f"{reason}; {status.match_reason}"})
                for status in context.retrieval_statuses
            ],
        }
    )


def _match_reason(
    score: float,
    min_score: float,
    exact_terms: Iterable[tuple[str, float]],
    document: _KnowledgeDocument,
    query_tokens: set[str],
) -> str:
    exact_terms = list(exact_terms)
    overlap = len(query_tokens & document.tokens)
    exact_count = sum(1 for term, _weight in exact_terms if normalize_text(term).lower() in normalize_text(document.text).lower())
    parts = [f"score {score} >= min_score {min_score}", f"token_overlap={overlap}"]
    if exact_count:
        parts.append(f"exact_term_matches={exact_count}")
    return "; ".join(parts)


def _embedding_match_reason(
    score: float,
    min_score: float,
    query_vector: list[float],
    document: _KnowledgeDocument,
    exact_terms: Iterable[tuple[str, float]],
    query_tokens: set[str],
) -> str:
    exact_terms = list(exact_terms)
    overlap = len(query_tokens & document.tokens)
    exact_count = sum(1 for term, _weight in exact_terms if normalize_text(term).lower() in normalize_text(document.text).lower())
    parts = [f"embedding_score {score} >= min_score {min_score}", f"token_overlap={overlap}", f"vector_dimensions={len(query_vector)}"]
    if exact_count:
        parts.append(f"exact_term_matches={exact_count}")
    return "; ".join(parts)


def _exact_terms_for(kb_type: str, extraction: StructuredExtractionResult | None) -> list[tuple[str, float]]:
    if extraction is None:
        return []
    exact_terms: list[tuple[str, float]] = []
    if kb_type == "client":
        exact_terms.extend((value, 8.0) for value in extraction.values("company_name"))
        exact_terms.extend((value, 12.0) for value in extraction.values("credit_code"))
        exact_terms.extend((value, 4.0) for value in extraction.values("legal_representative"))
        exact_terms.extend((value, 2.0) for value in extraction.values("contract_id"))
    else:
        exact_terms.extend((value, 3.0) for value in extraction.values("company_name"))
        exact_terms.extend((value, 2.0) for value in extraction.values("contract_id"))
    return exact_terms


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    ascii_tokens = re.findall(r"[a-z0-9][a-z0-9\-_/]{1,}", lowered)
    chinese_segments = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    chinese_tokens: list[str] = []
    for segment in chinese_segments:
        chinese_tokens.append(segment)
        if len(segment) <= 4:
            continue
        for index in range(len(segment) - 1):
            chinese_tokens.append(segment[index : index + 2])
    return {token for token in ascii_tokens + chinese_tokens if token}
