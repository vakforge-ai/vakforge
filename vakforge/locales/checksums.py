"""Checksum validators used by PII patterns to reject look-alike digit strings.

Pure functions, standard library only. Each accepts the matched text with separators.
"""

from __future__ import annotations

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def luhn_valid(text: str) -> bool:
    """Payment card numbers (13 to 19 digits)."""
    digits = _digits(text)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def verhoeff_valid(text: str) -> bool:
    """Verhoeff check digit, used by Aadhaar numbers."""
    c = 0
    for i, ch in enumerate(reversed(_digits(text))):
        c = _D[c][_P[i % 8][int(ch)]]
    return bool(_digits(text)) and c == 0


def verhoeff_digit(text: str) -> int:
    """Check digit to append to `text` so the result passes `verhoeff_valid`."""
    c = 0
    for i, ch in enumerate(reversed(_digits(text))):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return _INV[c]


def iban_valid(text: str) -> bool:
    """ISO 13616 mod-97 check."""
    s = "".join(text.split()).upper()
    if not 15 <= len(s) <= 34 or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    rearranged = s[4:] + s[:4]
    try:
        number = "".join(str(int(ch, 36)) for ch in rearranged)
    except ValueError:
        return False
    return int(number) % 97 == 1
