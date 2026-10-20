from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import StructuredEntity, StructuredExtractionResult, TextChunk
from app.rag import retrieval
from app.rag.embeddings import EmbeddingModelLoadError
from app.rag.retrieval import build_knowledge_context
from app.validators.rag_rules import check_knowledge_alignment


class FakeEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "星河" in text or "91310000MA1K000001" in text:
                vectors.append([1.0, 0.0])
            elif "完全不同" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.2, 0.0])
        return vectors


def _chunks() -> list[TextChunk]:
    return [
        TextChunk(text="甲方：上海星河科技股份有限公司，统一社会信用代码：91310000MA1K000001。", location="段落1")
    ]


def _extraction() -> StructuredExtractionResult:
    return StructuredExtractionResult(
        mode="mock",
        entities=[
            StructuredEntity(
                entity_type="company_name",
                value="上海星河科技股份有限公司",
                source_location="段落1",
            ),
            StructuredEntity(
                entity_type="credit_code",
                value="91310000MA1K000001",
                source_location="段落1",
            ),
        ],
    )


def _write_client(root: Path, payload: dict) -> None:
    clients = root / "clients"
    clients.mkdir(parents=True, exist_ok=True)
    (clients / f"{payload['id']}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_default_backend_uses_lexical(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("RAG_RETRIEVAL_BACKEND", raising=False)
    _write_client(
        tmp_path,
        {
            "id": "client-star-river",
            "title": "上海星河科技股份有限公司",
            "legal_name": "上海星河科技股份有限公司",
            "credit_code": "91310000MA1K000001",
        },
    )

    context = build_knowledge_context(_chunks(), _extraction(), kb_root=tmp_path)

    assert context.client_profile is not None
    assert context.status_for("client").status == "matched"
    assert "embedding" not in context.client_profile.match_reason


def test_embedding_backend_provider_unavailable_falls_back_to_lexical(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RAG_RETRIEVAL_BACKEND", "embedding")
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "none")
    _write_client(
        tmp_path,
        {
            "id": "client-star-river",
            "title": "上海星河科技股份有限公司",
            "legal_name": "上海星河科技股份有限公司",
            "credit_code": "91310000MA1K000001",
        },
    )

    context = build_knowledge_context(_chunks(), _extraction(), kb_root=tmp_path)

    assert context.client_profile is not None
    assert context.status_for("client").status == "matched"
    assert "embedding_unavailable_fallback_lexical" in context.status_for("client").match_reason
    assert "embedding_unavailable_fallback_lexical" in context.client_profile.match_reason


def test_embedding_backend_model_load_failure_falls_back_to_lexical(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RAG_RETRIEVAL_BACKEND", "embedding")
    _write_client(
        tmp_path,
        {
            "id": "client-star-river",
            "title": "上海星河科技股份有限公司",
            "legal_name": "上海星河科技股份有限公司",
            "credit_code": "91310000MA1K000001",
        },
    )

    def fail_provider(_settings):
        raise EmbeddingModelLoadError("model failed")

    monkeypatch.setattr(retrieval, "get_embedding_provider", fail_provider)

    context = build_knowledge_context(_chunks(), _extraction(), kb_root=tmp_path)

    assert context.client_profile is not None
    assert "embedding_model_load_failed_fallback_lexical" in context.status_for("client").match_reason


def test_fake_embedding_provider_returns_correct_match(tmp_path: Path):
    _write_client(
        tmp_path,
        {
            "id": "client-star-river",
            "title": "上海星河科技股份有限公司",
            "legal_name": "上海星河科技股份有限公司",
            "credit_code": "91310000MA1K000001",
        },
    )

    context = build_knowledge_context(
        _chunks(),
        _extraction(),
        kb_root=tmp_path,
        retrieval_backend="embedding",
        embedding_provider=FakeEmbeddingProvider(),
        min_scores={"client": 0.8},
    )

    assert context.client_profile is not None
    assert context.client_profile.doc_id == "client-star-river"
    assert context.status_for("client").status == "matched"
    assert "embedding_score" in context.client_profile.match_reason


def test_fake_embedding_low_score_does_not_emit_high_rag_mismatch(tmp_path: Path):
    _write_client(
        tmp_path,
        {
            "id": "client-other",
            "title": "完全不同客户有限公司",
            "legal_name": "完全不同客户有限公司",
            "credit_code": "000000000000000000",
        },
    )
    chunks = [TextChunk(text="一份不包含客户特征的合同文本。", location="段落1")]
    extraction = StructuredExtractionResult(
        mode="mock",
        entities=[
            StructuredEntity(
                entity_type="company_name",
                value="上海星河科技股份有限公司",
                source_location="段落1",
            )
        ],
    )

    context = build_knowledge_context(
        chunks,
        extraction,
        kb_root=tmp_path,
        retrieval_backend="embedding",
        embedding_provider=FakeEmbeddingProvider(),
        min_scores={"client": 0.95},
    )

    assert context.client_profile is None
    assert context.status_for("client").status in {"low_confidence_match", "no_match"}
    assert "embedding" in context.status_for("client").match_reason
    findings = check_knowledge_alignment(chunks, extraction, context)
    assert not any(finding.risk_type == "CLIENT_PROFILE_MISMATCH" and finding.severity == "high" for finding in findings)
