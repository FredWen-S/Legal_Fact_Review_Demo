from __future__ import annotations

from app.models.schemas import ExtractedItem, TextChunk


def extract_with_llm(chunks: list[TextChunk], enabled: bool = False) -> list[ExtractedItem]:
    """Reserved extension point. Disabled by default for privacy and offline use."""
    if not enabled:
        return []
    raise RuntimeError("LLM extraction is intentionally not configured in this local demo.")
