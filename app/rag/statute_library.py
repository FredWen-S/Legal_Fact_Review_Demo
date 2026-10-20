from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


STATUTE_ROOT = Path(__file__).resolve().parents[2] / "kb" / "statutes"
_PRC_PREFIX = "中华人民共和国"
_PARENTHETICAL = re.compile(r"[（(][^（）()]*[）)]")


@dataclass(frozen=True)
class StatuteReference:
    doc_id: str
    title: str
    short_name: str
    aliases: tuple[str, ...]
    status: str
    effective_date: str | None
    repealed_date: str | None
    replaced_by: str | None
    article_count: int | None
    version_note: str | None
    path: Path

    @property
    def is_repealed(self) -> bool:
        return self.status == "repealed"

    def names(self) -> tuple[str, ...]:
        return (self.title, self.short_name, *self.aliases)


def canonical_law_name(name: str) -> str:
    """Normalize a cited law name: drop whitespace, version notes in brackets and the PRC prefix."""
    text = re.sub(r"\s+", "", name)
    text = _PARENTHETICAL.sub("", text)
    if text.startswith(_PRC_PREFIX) and len(text) > len(_PRC_PREFIX):
        text = text[len(_PRC_PREFIX):]
    return text


@lru_cache(maxsize=4)
def load_statute_library(root: Path = STATUTE_ROOT) -> tuple[StatuteReference, ...]:
    if not root.exists():
        return ()
    statutes: list[StatuteReference] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("title"):
            continue
        title = str(payload["title"])
        article_count = payload.get("article_count")
        statutes.append(
            StatuteReference(
                doc_id=str(payload.get("id") or path.stem),
                title=title,
                short_name=str(payload.get("short_name") or canonical_law_name(title)),
                aliases=tuple(str(alias) for alias in payload.get("aliases", [])),
                status=str(payload.get("status") or "effective"),
                effective_date=payload.get("effective_date"),
                repealed_date=payload.get("repealed_date"),
                replaced_by=payload.get("replaced_by"),
                article_count=int(article_count) if isinstance(article_count, int) else None,
                version_note=payload.get("version_note"),
                path=path,
            )
        )
    return tuple(statutes)


def find_statute(name: str, root: Path = STATUTE_ROOT) -> StatuteReference | None:
    target = canonical_law_name(name)
    if not target:
        return None
    for statute in load_statute_library(root):
        if any(canonical_law_name(candidate) == target for candidate in statute.names()):
            return statute
    return None


def known_law_names(root: Path = STATUTE_ROOT) -> list[str]:
    """All titles, short names and aliases, longest first, for matching citations without 《》."""
    names: set[str] = set()
    for statute in load_statute_library(root):
        for candidate in statute.names():
            names.add(candidate)
            names.add(canonical_law_name(candidate))
    return sorted((name for name in names if name), key=len, reverse=True)
