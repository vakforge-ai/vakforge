import pytest

from vakforge.locales import get_pack

GB = get_pack("en-GB")


def found(text):
    return [(s.type, s.text) for s in GB.find_pii(text)]


def test_normalizer_spells_pounds():
    assert GB.normalize_text("That's £45.99, cheers!") == "that s 45.99 pounds cheers"


@pytest.mark.parametrize("ni", ["JG 10 37 59 A", "JG103759A", "AB 12 34 56 C"])
def test_ni_number_detected(ni):
    assert found(f"my NI is {ni} thanks") == [("ni_number", ni)]


@pytest.mark.parametrize("bad", ["GB123456A", "DQ123456C", "AB123456E", "ZZ123456A"])
def test_invalid_ni_ignored(bad):
    assert found(f"ref {bad}") == []


# Ofcom reserves 07700 900xxx and 020 7946 0xxx for fiction.
@pytest.mark.parametrize("phone", ["07700 900123", "+44 7700 900123", "020 7946 0018"])
def test_uk_phone_detected(phone):
    assert found(f"ring {phone} after five") == [("phone", phone)]


@pytest.mark.parametrize(
    "text", ["version 1.2.3", "postcode SW1A 1AA", "order 12345 6789", "call 0123"]
)
def test_no_false_positives(text):
    assert found(text) == []


def test_pack_metadata():
    assert GB.resolved("call_recording_consent") == "notice_required"
    assert GB.formats.date_order == "DMY"
    assert "iban" in {p.name for p in GB.all_pii_patterns()}
