"""Funções utilitárias para gestão de tags de CLPs."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List

_TAG_ALLOWED_CHARS = re.compile(r"[^a-z0-9_\-]+")
_SEPARATOR_PATTERN = re.compile(r"[,;\n]+")


def normalize_tag(value: str) -> str:
    """Normaliza uma única tag para formato slug."""
    cleaned = unicodedata.normalize('NFKD', value.strip().lower())
    cleaned = ''.join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = _TAG_ALLOWED_CHARS.sub("-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned


def parse_tags(raw: str | Iterable[str] | None) -> List[str]:
    if raw is None:
        return []

    if isinstance(raw, str):
        candidates = [chunk for chunk in _SEPARATOR_PATTERN.split(raw) if chunk.strip()]
    else:
        candidates = [str(item) for item in raw if str(item).strip()]

    normalised: List[str] = []
    seen = set()
    for candidate in candidates:
        slug = normalize_tag(candidate)
        if slug and slug not in seen:
            normalised.append(slug)
            seen.add(slug)
    return normalised
