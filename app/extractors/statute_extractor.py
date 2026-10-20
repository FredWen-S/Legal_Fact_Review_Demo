from __future__ import annotations

import re
from functools import lru_cache

from app.models.schemas import StructuredEntity, TextChunk
from app.rag.statute_library import canonical_law_name, find_statute, known_law_names


_NUMERAL = r"[零〇一二两三四五六七八九十百千\d]+"
_ARTICLE = re.compile(rf"第({_NUMERAL})条(?:第{_NUMERAL}款)?(?:第{_NUMERAL}项)?")
_ARTICLE_LIST = rf"(?:第{_NUMERAL}条(?:第{_NUMERAL}款)?(?:第{_NUMERAL}项)?(?:\s*[、，,及和与至]\s*)?)+"
_BRACKETED_CITATION = re.compile(rf"《(?P<law>[^《》\n]{{2,60}}?)》\s*(?P<articles>{_ARTICLE_LIST})")
_NORMALIZED_CITATION = re.compile(r"^《(?P<law>.+)》第(?P<article>\d+)条$")
_LAW_SUFFIXES = ("法", "法典", "条例", "规定", "解释", "办法", "规则", "决定")
_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000}


def extract_statute_entities(chunks: list[TextChunk]) -> list[StructuredEntity]:
    """Extract statute citations such as 《中华人民共和国民法典》第五百七十七条 or 民法典第577条.

    One entity is produced per cited article; references to contract clauses
    (e.g. 《技术服务合同》第三条) are ignored because the bracketed name is not a law.
    """
    entities: list[StructuredEntity] = []
    unbracketed = _unbracketed_pattern()
    for chunk in chunks:
        covered: list[tuple[int, int]] = []
        for match in _BRACKETED_CITATION.finditer(chunk.text):
            law = match.group("law").strip()
            if not canonical_law_name(law).endswith(_LAW_SUFFIXES):
                continue
            covered.append(match.span())
            entities.extend(_citation_entities(f"《{law}》", law, match.group("articles"), chunk))
        if unbracketed is None:
            continue
        for match in unbracketed.finditer(chunk.text):
            if any(start <= match.start() < end for start, end in covered):
                continue
            law = match.group("law")
            entities.extend(_citation_entities(law, law, match.group("articles"), chunk))
    return entities


def normalize_statute_citation(value: str) -> str | None:
    """Normalize a single citation string (e.g. from an LLM) to 《民法典》第577条; None if unparseable."""
    text = value.strip()
    bracketed = _BRACKETED_CITATION.search(text)
    if bracketed:
        law, articles = bracketed.group("law"), bracketed.group("articles")
    else:
        unbracketed = _unbracketed_pattern()
        match = unbracketed.search(text) if unbracketed else None
        if match is None:
            return None
        law, articles = match.group("law"), match.group("articles")
    article = _ARTICLE.search(articles)
    number = chinese_numeral_to_int(article.group(1)) if article else None
    if number is None:
        return None
    return _normalized(law, number)


def parse_normalized_citation(value: str | None) -> tuple[str, int] | None:
    match = _NORMALIZED_CITATION.match(value or "")
    if not match:
        return None
    return match.group("law"), int(match.group("article"))


def chinese_numeral_to_int(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    for char in text:
        if char in _DIGITS:
            current = _DIGITS[char]
        elif char in _UNITS:
            total += (current or 1) * _UNITS[char]
            current = 0
        else:
            return None
    total += current
    return total or None


def _citation_entities(prefix: str, law: str, articles: str, chunk: TextChunk) -> list[StructuredEntity]:
    entities: list[StructuredEntity] = []
    for article in _ARTICLE.finditer(articles):
        number = chinese_numeral_to_int(article.group(1))
        if number is None:
            continue
        value = f"{prefix}{article.group(0)}"
        entities.append(
            StructuredEntity(
                entity_type="statute_reference",
                value=value,
                normalized_value=_normalized(law, number),
                source_location=chunk.location,
                confidence=0.85,
                context=chunk.text[:300],
            )
        )
    return entities


def _normalized(law: str, number: int) -> str:
    statute = find_statute(law)
    name = statute.short_name if statute else canonical_law_name(law)
    return f"《{name}》第{number}条"


def _unbracketed_pattern() -> re.Pattern[str] | None:
    return _compile_unbracketed(tuple(known_law_names()))


@lru_cache(maxsize=4)
def _compile_unbracketed(names: tuple[str, ...]) -> re.Pattern[str] | None:
    if not names:
        return None
    alternation = "|".join(re.escape(name) for name in names)
    return re.compile(rf"(?P<law>{alternation})(?P<articles>{_ARTICLE_LIST})")
