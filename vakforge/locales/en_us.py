"""en-US: US English. Dollars, MDY dates, NANP phones, SSN."""

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
from vakforge.locales.en import EnglishPack

# SSA never issues area 000, 666 or 900-999, group 00, or serial 0000.
SSN = PIIPattern(
    "ssn",
    re.compile(r"\b(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}\b"),
)
# Nine digits with no separators are only an SSN when something nearby says so; bare
# nine-digit strings are far more often order or account numbers.
SSN_COMPACT = PIIPattern(
    "ssn",
    re.compile(r"\b(?!000|666|9\d\d)\d{3}(?!00)\d{2}(?!0000)\d{4}\b"),
    # Anything but a digit may sit between the cue and the number ("ssn is", "ssn number:"),
    # because missing a real SSN is worse than redacting one order number too many.
    context_require=re.compile(
        r"(?i)\b(ssn|social(?:\s+security)?(?:\s+number)?|tin)\b[^0-9]{0,12}$"
    ),
)
# NANP: area and exchange codes start 2-9; optional +1 and common separators. A ten-digit
# order or account number matches this shape too, so the introducing word decides.
PHONE_US = PIIPattern(
    "phone",
    re.compile(r"(?<![\w+])(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?[2-9]\d{2}[\s.-]?\d{4}\b"),
    context_deny=reference_cue(*REFERENCE_WORDS),
)


@register
class EnUS(EnglishPack):
    id = "en-US"
    name = "US English"
    languages = ["en-US"]
    parent = "en"
    formats = LocaleFormats(
        currency_symbols=("US$", "$"),
        currency_words=("dollars", "bucks", "grand"),
        date_order="MDY",
        phone_example="(415) 555-0134",
        postal_example="94107 or 94107-1234",
    )
    pii_patterns = [SSN, SSN_COMPACT, PHONE_US]
    call_recording_consent = "varies_by_state"
    privacy_notes = PrivacyNotes(
        summary=(
            "No single federal privacy law. State laws apply, for example California "
            "CCPA/CPRA. Illinois BIPA treats voiceprints as biometric identifiers. "
            "Call-recording consent varies by state; several, including California, "
            "require all parties to consent."
        ),
        links=(
            "https://oag.ca.gov/privacy/ccpa",
            "https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004",
        ),
    )
    recipe_support = {
        "lfm25-audio": "native",
        "moshi-lora": "native",
        "qwen-omni": "native",
        "cascade": "native",
    }
