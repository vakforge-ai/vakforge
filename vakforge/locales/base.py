"""LocalePack base and registry. Everything language- or market-specific lives in a pack.

A pack declares its formats, PII patterns, consent rule and per-recipe support as class
attributes. Children name a `parent`; list-valued rules (PII patterns) and language tags are
inherited and extended, scalar settings are overridden. Core code asks the pack and never
branches on a language string (docs/LOCALE_PACKS.md).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Literal

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)

Consent = Literal["one_party", "all_party", "varies_by_state", "notice_required"]
Support = Literal["native", "understand_only", "cascade", "unsupported"]
DateOrder = Literal["MDY", "DMY", "YMD"]


# Characters before a match that the context patterns inspect. Long enough to hold a full
# cue phrase such as "my social security number is ".
CONTEXT_WINDOW = 40


@dataclass(frozen=True)
class PIIPattern:
    """A regex for one kind of personal data, with optional checks to cut false hits.

    `validate` runs a checksum on the matched text. The two context patterns look at the
    characters just before a match: `context_deny` rejects it ("order 9876543210" is not a
    phone number), `context_require` demands a cue ("ssn 123456789" is, a bare nine-digit
    string is not).
    """

    name: str
    regex: re.Pattern[str]
    validate: Callable[[str], bool] | None = None
    context_deny: re.Pattern[str] | None = None
    context_require: re.Pattern[str] | None = None

    def finditer(self, text: str):
        for m in self.regex.finditer(text):
            if self.validate is not None and not self.validate(m.group(0)):
                continue
            before = text[max(0, m.start() - CONTEXT_WINDOW) : m.start()]
            if self.context_deny is not None and self.context_deny.search(before):
                continue
            if self.context_require is not None and not self.context_require.search(before):
                continue
            yield m


def reference_cue(*words: str) -> re.Pattern[str]:
    """A `context_deny` pattern for numbers introduced as a reference, not a phone.

    Matches the cue word followed only by filler: "order 9876543210",
    "order number is 9876543210", "my order id is 9876543210", "invoice no. 9876543210".

    It deliberately does not match "order cancel karke mera 9876543210", where unrelated
    words sit between the cue and the digits and the number really is a phone. That is why
    the filler is an explicit word list rather than a character budget: a plain "any N
    characters" window silently suppresses real phone numbers a couple of words later.
    """
    cues = "|".join(words)
    filler = r"(?:\s+(?:number|no|num|nbr|id|ref|code|is|was|the|my|your|our))*"
    return re.compile(rf"(?i)\b(?:{cues})\b{filler}\s*[:#=.\-]?\s*$")


# Words that introduce a reference number in English-speaking markets. Packs extend this.
REFERENCE_WORDS = (
    "order",
    "purchase",
    "invoice",
    "ref",
    "reference",
    "ticket",
    "txn",
    "transaction",
    "receipt",
    "policy",
    "account",
    "acc",
    "a/c",
    "card",
    "imei",
    "sku",
    "awb",
    "pnr",
    "gst",
    "tracking",
    "case",
    "claim",
    "booking",
    "confirmation",
    "member",
    "membership",
)


@dataclass(frozen=True)
class PIISpan:
    """One detected piece of personal data in a text."""

    type: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class LocaleFormats:
    currency_symbols: tuple[str, ...] = ()
    currency_words: tuple[str, ...] = ()
    date_order: DateOrder = "DMY"
    phone_example: str = ""
    postal_example: str = ""


@dataclass(frozen=True)
class PrivacyNotes:
    """Short, sourced starting points shown by `prepare`. Not legal advice."""

    summary: str
    links: tuple[str, ...] = field(default_factory=tuple)


class LocalePack:
    """Subclass and set the class attributes. Register with `register()`."""

    id: ClassVar[str]
    name: ClassVar[str] = ""
    languages: ClassVar[list[str]]
    parent: ClassVar[str | None] = None

    formats: ClassVar[LocaleFormats | None] = None
    pii_patterns: ClassVar[list[PIIPattern]] = []
    call_recording_consent: ClassVar[Consent | None] = None
    privacy_notes: ClassVar[PrivacyNotes | None] = None
    recipe_support: ClassVar[dict[str, Support]] = {}

    # ---- inheritance helpers -------------------------------------------------------

    def parent_pack(self) -> LocalePack | None:
        return get_pack(self.parent) if self.parent else None

    def all_languages(self) -> set[str]:
        """Tags this pack accepts on a turn, including inherited ones."""
        langs = set(self.languages)
        if parent := self.parent_pack():
            langs |= parent.all_languages()
        return langs

    def all_pii_patterns(self) -> list[PIIPattern]:
        """Own patterns first, then inherited ones not overridden by name."""
        own = list(self.pii_patterns)
        names = {p.name for p in own}
        if parent := self.parent_pack():
            own += [p for p in parent.all_pii_patterns() if p.name not in names]
        return own

    def resolved(self, attr: str):
        """First non-empty value of a scalar setting walking up the parent chain."""
        value = getattr(self, attr)
        if value:
            return value
        parent = self.parent_pack()
        return parent.resolved(attr) if parent else value

    # ---- text hooks ----------------------------------------------------------------

    def detect_lang(self, text: str) -> str:
        """Per-turn language tag. Default: the pack's first language."""
        return self.languages[0]

    def lang_mix(self, text: str) -> list[str]:
        """Every language present in a turn, primary first.

        Packs for code-switched locales override this. The default reports one language,
        which is correct for packs whose speakers do not mix languages mid-turn.
        """
        return [self.detect_lang(text)]

    def normalize_text(self, text: str) -> str:
        """Text normalization for WER. Default: lowercase, strip punctuation, collapse spaces."""
        return " ".join(_PUNCT.sub(" ", text.lower()).split())

    def find_pii(self, text: str) -> list[PIISpan]:
        """Every PII match, earliest first; overlapping matches keep the longest span."""
        hits = [
            PIISpan(p.name, m.start(), m.end(), m.group(0))
            for p in self.all_pii_patterns()
            for m in p.finditer(text)
        ]
        hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
        kept: list[PIISpan] = []
        for h in hits:
            if kept and h.start < kept[-1].end:
                continue
            kept.append(h)
        return kept


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
