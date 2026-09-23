"""`en` parent pack: rules shared by every English locale.

Owns patterns that are the same everywhere English is spoken (email, payment cards, IBAN)
and the English WER normalizer. Market packs live in their own modules and inherit from it:
`en_us`, `en_gb`, `en_in` (and `hi_latn_in` through `en_in`).
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
    # Case-insensitive, because transcripts arrive lowercased and `iban_valid` upper-cases
    # before checking; a case-sensitive pattern rejected text the validator would accept.
    #
    # The groups are spelled out rather than using a loose `(?: ?[A-Z0-9]){11,30}`: once the
    # pattern ignores case, a loose run happily eats the space and the next word ("… 7654 32
    # please"), and the over-long match then fails the checksum, so the IBAN is missed
    # entirely. An IBAN is written either contiguously or in groups of four.
    re.compile(
        r"\b[A-Za-z]{2}\d{2}"
        r"(?:[A-Za-z0-9]{11,30}|(?:[ -][A-Za-z0-9]{4})*[ -][A-Za-z0-9]{1,4})"
        r"\b"
    ),
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
