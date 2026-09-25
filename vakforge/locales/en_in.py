"""en-IN: Indian English. Rupees with lakh/crore, DMY dates, +91 mobiles, Aadhaar, PAN."""

from __future__ import annotations

import re

from vakforge.locales.base import (
    REFERENCE_WORDS,
    LocaleFormats,
    PIIPattern,
    PrivacyNotes,
    reference_cue,
    register,
)
from vakforge.locales.checksums import verhoeff_valid
from vakforge.locales.en import EnglishPack

# 12 digits, first digit 2-9, usually grouped 4-4-4; last digit is a Verhoeff check digit.
AADHAAR = PIIPattern(
    "aadhaar",
    re.compile(r"(?<![\d-])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\d-])"),
    validate=verhoeff_valid,
)
# AAAPA9999A; the 4th letter encodes the holder type (P person, C company, ...).
PAN = PIIPattern("pan", re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]\b", re.I))
# Mobile numbers start 6-9; optional +91 or leading 0. Ten digits introduced as an order,
# invoice or AWB number are a reference, not a phone number.
PHONE_IN = PIIPattern(
    "phone",
    re.compile(r"(?<![\d+])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),
    context_deny=reference_cue(*REFERENCE_WORDS),
)

_SYMBOLS = r"(?:₹|rs\.?|inr)"
_AMOUNT = re.compile(
    rf"{_SYMBOLS}\s?(\d[\d,]*(?:\.\d+)?)(\s?(?:lakhs?|crores?|k|thousand))?",
    re.I,
)
_INDIAN_GROUPING = re.compile(r"(?<=\d),(?=\d)")


@register
class EnIN(EnglishPack):
    id = "en-IN"
    name = "Indian English"
    languages = ["en-IN"]
    parent = "en"
    formats = LocaleFormats(
        currency_symbols=("₹", "Rs.", "Rs", "INR"),
        currency_words=("rupees", "lakh", "crore"),
        date_order="DMY",
        phone_example="+91 74281 96530",
        postal_example="560001",
    )
    pii_patterns = [AADHAAR, PAN, PHONE_IN]
    call_recording_consent = "notice_required"
    privacy_notes = PrivacyNotes(
        summary=(
            "The Digital Personal Data Protection Act, 2023 and its rules apply: give notice "
            "and obtain consent before processing personal data, and honour withdrawal. "
            "Aadhaar numbers must not be stored or displayed in full."
        ),
        links=("https://www.meity.gov.in/data-protection-framework",),
    )
    recipe_support = {
        "lfm25-audio": "native",
        "moshi-lora": "native",
        "qwen-omni": "native",
        "cascade": "native",
    }

    def normalize_text(self, text: str) -> str:
        """Indian digit grouping and rupee amounts ("₹2 lakh" -> "2 lakh rupees") first."""
        t = _INDIAN_GROUPING.sub("", text)
        t = _AMOUNT.sub(lambda m: f"{m.group(1)}{m.group(2) or ''} rupees", t)
        return super().normalize_text(t)
