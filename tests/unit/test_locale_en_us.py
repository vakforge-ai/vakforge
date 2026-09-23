import pytest

from vakforge.locales import get_pack

US = get_pack("en-US")


def found(text):
    return [(s.type, s.text) for s in US.find_pii(text)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("That'll be $1,200.50, OK?", "that ll be 1200.50 dollars ok"),
        ("US$ 45 plus tax", "45 dollars plus tax"),
    ],
)
def test_normalizer_spells_dollars(raw, expected):
    assert US.normalize_text(raw) == expected


@pytest.mark.parametrize("ssn", ["123-45-6789", "536 22 1234"])
def test_ssn_detected(ssn):
    assert found(f"my social is {ssn}.") == [("ssn", ssn)]


@pytest.mark.parametrize("bad", ["000-12-3456", "666-12-3456", "912-12-3456", "123-00-4567"])
def test_invalid_ssn_ranges_ignored(bad):
    assert [t for t, _ in found(f"id {bad}")] != ["ssn"]


@pytest.mark.parametrize(
    "text",
    [
        "ssn 536221234",
        "my SSN is 536221234",
        "social security number is 536221234",
        "TIN: 536221234",
    ],
)
def test_compact_ssn_detected_after_a_cue(text):
    assert found(text) == [("ssn", "536221234")]


@pytest.mark.parametrize("text", ["order 536221234", "reference 536221234", "536221234"])
def test_compact_ssn_needs_a_cue(text):
    assert found(text) == []


@pytest.mark.parametrize("phone", ["(415) 555-0134", "+1 212.555.0199", "650-253-0000"])
def test_us_phone_detected(phone):
    assert found(f"call {phone} tomorrow") == [("phone", phone)]


@pytest.mark.parametrize("text", ["order 123-456", "zip 94107", "in 1999 we moved", "room 101-555"])
def test_no_false_positives(text):
    assert found(text) == []


# A ten-digit account or order number has the same shape as a NANP number.
@pytest.mark.parametrize(
    "text", ["order number is 4155550134", "account no. 4155550134", "case #4155550134"]
)
def test_reference_numbers_are_not_phones(text):
    assert found(text) == []


@pytest.mark.parametrize(
    "text", ["call me at (415) 555-0134", "the order shipped, call 415 555 0134"]
)
def test_real_phones_survive_a_nearby_cue_word(text):
    assert [t for t, _ in found(text)] == ["phone"]


def test_pack_metadata():
    assert US.resolved("call_recording_consent") == "varies_by_state"
    assert US.formats.date_order == "MDY"
    assert set(US.recipe_support.values()) == {"native"}
    assert "email" in {p.name for p in US.all_pii_patterns()}
