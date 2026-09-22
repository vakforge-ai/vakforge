"""en-GB: UK English. Pounds, DMY dates, UK phones, National Insurance numbers."""

from __future__ import annotations

import re

from vakforge.locales.base import LocaleFormats, PIIPattern, PrivacyNotes, register
from vakforge.locales.en import EnglishPack

# HMRC format: two prefix letters (first not D F I Q U V, second not D F I O Q U V),
# never the prefixes BG GB KN NK NT TN ZZ; six digits; suffix A-D. Spaces optional.
NI_NUMBER = PIIPattern(
    "ni_number",
    re.compile(
        r"\b(?!BG|GB|KN|NK|NT|TN|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]"
        r" ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b",
        re.I,  # transcripts arrive lowercased; a redactor that only sees capitals leaks
    ),
)
# Mobiles (07xxx / +44 7xxx) and geographic landlines (01x / 02x).
PHONE_GB = PIIPattern(
    "phone",
    re.compile(
        r"(?<![\d+])(?:(?:\+44\s?|0)7\d{3}\s?\d{3}\s?\d{3}"
        r"|(?:\+44\s?|0)[12]\d{1,3}\s?\d{3,4}\s?\d{3,4})\b"
    ),
)


@register
class EnGB(EnglishPack):
    id = "en-GB"
    name = "UK English"
    languages = ["en-GB"]
    parent = "en"
    formats = LocaleFormats(
        currency_symbols=("£",),
        currency_words=("pounds", "quid"),
        date_order="DMY",
        phone_example="07700 900123",
        postal_example="SW1A 1AA",
    )
    pii_patterns = [NI_NUMBER, PHONE_GB]
    call_recording_consent = "notice_required"
    privacy_notes = PrivacyNotes(
        summary=(
            "UK GDPR and the Data Protection Act 2018 apply. Recording and processing calls "
            "needs a lawful basis and notice to callers. Voice used to identify someone is "
            "special-category biometric data. ICO guidance applies."
        ),
        links=("https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/",),
    )
    recipe_support = {
        "lfm25-audio": "native",
        "moshi-lora": "native",
        "qwen-omni": "native",
        "cascade": "native",
    }
