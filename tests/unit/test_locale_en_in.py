import pytest

from vakforge.locales import get_pack
from vakforge.locales.checksums import verhoeff_digit

IN = get_pack("en-IN")


def found(text):
    return [(s.type, s.text) for s in IN.find_pii(text)]


def aadhaar(base11: str) -> str:
    full = base11 + str(verhoeff_digit(base11))
    return f"{full[:4]} {full[4:8]} {full[8:]}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Charge ₹500 hoga.", "charge 500 rupees hoga"),
        ("Budget is ₹2 lakh", "budget is 2 lakh rupees"),
        ("Rs. 1,50,000 only", "150000 rupees only"),
        ("INR 2.5 crore deal", "2.5 crore rupees deal"),
        ("total 12,34,567 units", "total 1234567 units"),
    ],
)
def test_normalizer_indian_amounts(raw, expected):
    assert IN.normalize_text(raw) == expected


def test_valid_aadhaar_detected():
    number = aadhaar("23412341234")
    assert found(f"aadhaar {number} hai") == [("aadhaar", number)]


@pytest.mark.parametrize("prefix", ["0341234123", "1341234123"])
def test_aadhaar_cannot_start_with_0_or_1(prefix):
    number = prefix + "4" + str(verhoeff_digit(prefix + "4"))
    assert "aadhaar" not in [t for t, _ in found(f"id {number}")]


def test_aadhaar_with_bad_check_digit_ignored():
    good = aadhaar("23412341234").replace(" ", "")
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    assert "aadhaar" not in [t for t, _ in found(f"id {bad}")]


@pytest.mark.parametrize("pan", ["ABCPE1234F", "AAACT5678K"])
def test_pan_detected(pan):
    assert found(f"PAN {pan} please") == [("pan", pan)]


@pytest.mark.parametrize("bad", ["ABCXE1234F", "ABCP1234F", "ABCPE12345"])
def test_invalid_pan_ignored(bad):
    assert found(f"ref {bad}") == []


@pytest.mark.parametrize("phone", ["+91 98765 43210", "98765-43210", "9876543210", "09876543210"])
def test_indian_mobile_detected(phone):
    assert found(f"call {phone} kal") == [("phone", phone)]


@pytest.mark.parametrize("text", ["PIN 560001", "5876543210 is not a mobile", "order 12345 67890"])
def test_no_false_positives(text):
    assert found(text) == []


def test_pack_metadata():
    assert IN.resolved("call_recording_consent") == "notice_required"
    assert "Digital Personal Data Protection Act, 2023" in IN.privacy_notes.summary
    assert {"email", "card_number", "aadhaar", "pan", "phone"} <= {
        p.name for p in IN.all_pii_patterns()
    }
