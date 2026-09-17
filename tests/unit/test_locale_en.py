import pytest

from vakforge.locales import get_pack

EN = get_pack("en")


def types(text, pack=EN):
    return [(s.type, s.text) for s in pack.find_pii(text)]


# ---- normalizer (golden cases) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Hello, World!  ", "hello world"),
        ("It's 3.5 km & 20% off.", "it s 3.5 km and 20 percent off"),
        ("Order 1,250 units", "order 1250 units"),
        ("Version 2.0.1?", "version 2.0.1"),
    ],
)
def test_normalizer_golden(raw, expected):
    assert EN.normalize_text(raw) == expected


# ---- shared PII: positives -----------------------------------------------------------


def test_email_detected():
    assert types("mail me at priya.k+support@sun-care.co.in today") == [
        ("email", "priya.k+support@sun-care.co.in")
    ]


@pytest.mark.parametrize("card", ["4111 1111 1111 1111", "5555-5555-5555-4444", "378282246310005"])
def test_valid_cards_detected(card):
    assert types(f"card {card} thanks") == [("card_number", card)]


def test_iban_detected():
    assert types("pay into GB82 WEST 1234 5698 7654 32 please") == [
        ("iban", "GB82 WEST 1234 5698 7654 32")
    ]


# ---- shared PII: negatives -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "card 4111 1111 1111 1112 fails Luhn",
        "ticket 2026-09-17-0001 is open",
        "call me at noon",
        "user at example dot com",
        "GB82 WEST 1234 5698 7654 33 has a bad checksum",
    ],
)
def test_no_false_positives(text):
    assert types(text) == []


def test_children_inherit_shared_patterns():
    for pack_id in ("en-US", "en-GB", "en-IN"):
        names = {p.name for p in get_pack(pack_id).all_pii_patterns()}
        assert {"email", "card_number", "iban"} <= names
