"""LocalePack base and registry. Everything language- or market-specific lives in a pack.

Phase 0 ships the skeleton: identity, language tags, inheritance, and the two text hooks
core needs for validation and WER. Formats, PII patterns, generators and recipe support
land in Phase 1 (docs/LOCALE_PACKS.md).
"""

from __future__ import annotations

import re
from typing import ClassVar

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


class LocalePack:
    """Subclass and set the class attributes. Register with `register()`."""

    id: ClassVar[str]
    languages: ClassVar[list[str]]
    parent: ClassVar[str | None] = None

    def all_languages(self) -> set[str]:
        """Tags this pack accepts on a turn, including inherited ones."""
        langs = set(self.languages)
        if self.parent:
            langs |= get_pack(self.parent).all_languages()
        return langs

    def detect_lang(self, text: str) -> str:
        """Per-turn language tag. Default: the pack's first language."""
        return self.languages[0]

    def normalize_text(self, text: str) -> str:
        """Text normalization for WER. Default: lowercase, strip punctuation, collapse spaces."""
        return " ".join(_PUNCT.sub(" ", text.lower()).split())


_REGISTRY: dict[str, LocalePack] = {}


def register(cls: type[LocalePack]) -> type[LocalePack]:
    """Class decorator: instantiate and register a pack by id."""
    _REGISTRY[cls.id] = cls()
    return cls


def get_pack(pack_id: str) -> LocalePack:
    try:
        return _REGISTRY[pack_id]
    except KeyError:
        raise KeyError(f"unknown locale pack {pack_id!r}; known: {sorted(_REGISTRY)}") from None


def list_packs() -> list[str]:
    return sorted(_REGISTRY)
