import pytest

from vakforge.locales.checksums import iban_valid, luhn_valid, verhoeff_digit, verhoeff_valid


@pytest.mark.parametrize(
    "number",
    ["4111 1111 1111 1111", "5555-5555-5555-4444", "378282246310005"],  # published test cards
)
def test_luhn_accepts_known_test_cards(number):
    assert luhn_valid(number)


@pytest.mark.parametrize("number", ["4111 1111 1111 1112", "1234", "12345678901234567890"])
def test_luhn_rejects(number):
    assert not luhn_valid(number)


def test_verhoeff_reference_example():
    # Worked example from Verhoeff's scheme: 236 has check digit 3.
    assert verhoeff_digit("236") == 3
    assert verhoeff_valid("2363")
    assert not verhoeff_valid("2364")


def test_verhoeff_round_trip_detects_single_digit_errors():
    base = "23412341234"
    full = base + str(verhoeff_digit(base))
    assert verhoeff_valid(full)
    for i in range(len(full)):
        wrong = full[:i] + str((int(full[i]) + 1) % 10) + full[i + 1 :]
        assert not verhoeff_valid(wrong)


@pytest.mark.parametrize("iban", ["GB82 WEST 1234 5698 7654 32", "DE89370400440532013000"])
def test_iban_accepts_registry_examples(iban):
    assert iban_valid(iban)


@pytest.mark.parametrize("iban", ["GB82 WEST 1234 5698 7654 33", "GB82", "1234567890123456"])
def test_iban_rejects(iban):
    assert not iban_valid(iban)


def _mod97(s: str) -> int:
    rearranged = s[4:] + s[:4]
    return int("".join(str(int(ch, 36)) for ch in rearranged)) % 97


def test_iban_rejects_invented_country_that_passes_mod_97():
    # Built so the mod-97 check succeeds; only the country registry rejects it.
    candidates = [f"ZZ{check:02d}AAAAAAAAAAAAAAAA" for check in range(2, 100)]
    passing = [c for c in candidates if _mod97(c) == 1]
    assert passing, "no check digit made the mod-97 pass"
    assert not any(iban_valid(c) for c in passing)


def test_iban_rejects_right_country_wrong_length():
    # GB is 22 characters; a 24-character GB number is not an IBAN whatever mod-97 says.
    assert not iban_valid("GB82 WEST 1234 5698 7654 3200")
