"""English packs: `en` parent with shared rules, plus en-US, en-GB, en-IN.

The parent owns patterns that are the same everywhere English is spoken (email, payment
cards, IBAN) and the English WER normalizer. Children add market formats, national IDs and
consent rules; they split into their own modules as they grow.
"""

from __future__ import annotations

import re

from vakforge.locales.base import LocaleFormats, LocalePack, PIIPattern, register
from vakforge.locales.checksums import iban_valid, luhn_valid

EMAIL = PIIPattern(
    "email",
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)
CARD = PIIPattern(
    "card_number",
    re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"),
    validate=luhn_valid,
)
IBAN = PIIPattern(
    "iban",
    re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),
    validate=iban_valid,
)

_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
_PERCENT = re.compile(r"(?<=\d)\s?%")
# keep "." only between digits (decimals); everything else that is not a word char goes
_PUNCT_EXCEPT_DECIMAL = re.compile(r"(?!(?<=\d)\.(?=\d))[^\w\s]")


class EnglishPack(LocalePack):
    """Shared English behaviour. Children override `formats` for their currency."""

    def normalize_text(self, text: str) -> str:
        """Lowercase; spell out currency and percent; drop thousands separators and punctuation."""
        t = text.lower()
        formats = self.resolved("formats") or LocaleFormats()
        if formats.currency_symbols and formats.currency_words:
            word = formats.currency_words[0]
            symbols = "|".join(re.escape(s) for s in formats.currency_symbols)
            t = re.sub(rf"(?:{symbols})\s?(\d[\d,]*(?:\.\d+)?)", rf"\1 {word}", t, flags=re.I)
        t = _THOUSANDS.sub("", t)
        t = _PERCENT.sub(" percent", t)
        t = t.replace("&", " and ")
        t = _PUNCT_EXCEPT_DECIMAL.sub(" ", t)
        return " ".join(t.split())


@register
class En(EnglishPack):
    id = "en"
    name = "English (shared)"
    languages = ["en"]
    pii_patterns = [EMAIL, CARD, IBAN]
