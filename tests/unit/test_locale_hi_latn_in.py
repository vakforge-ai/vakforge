import pytest

from vakforge.locales import get_pack

HI = get_pack("hi-Latn-IN")


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Haan, mera inverter kal se off hai.", "hi-Latn"),
        ("Ek minute, check karti hoon.", "hi-Latn"),
        ("Order status batao", "hi-Latn"),
        ("Namaste ji", "hi-Latn"),
        # Mostly English words around one or two Hindi verbs is still a Hinglish turn.
        ("Main order cancel kar do", "hi-Latn"),
        ("Please mera refund jaldi kar dijiye", "hi-Latn"),
        ("Delivery kab tak aayega", "hi-Latn"),
        ("मेरा ऑर्डर कहाँ है?", "hi"),
        ("Can you check my order status?", "en-IN"),
        ("Please do the needful by Monday", "en-IN"),
        ("I am in the main office to meet him", "en-IN"),
    ],
)
def test_detect_lang_golden(text, lang):
    assert HI.detect_lang(text) == lang


def test_lang_mix_reports_both_languages_in_code_switched_turn():
    assert HI.lang_mix("Order status batao please") == ["hi-Latn", "en-IN"]
    assert HI.lang_mix("Can you check my order?") == ["en-IN"]
    assert HI.lang_mix("मेरा order कहाँ है") == ["hi", "en-IN"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Haan ji, thik hai. Charge ₹500 hoga!", "haan ji theek hai charge 500 rupees hoga"),
        ("Nahin, acha nahi laga", "nahi accha nahi laga"),
        ("Budget ₹2 lakh tak hai", "budget 2 lakh rupees tak hai"),
        ("मेरा ऑर्डर कहाँ है?", "मेरा ऑर्डर कहाँ है"),
        ("नंबर ९८७६५ है", "नंबर 98765 है"),
        ("rate 3.5% hai", "rate 3.5 percent hai"),
    ],
)
def test_normalizer_golden(raw, expected):
    assert HI.normalize_text(raw) == expected


def test_inherits_indian_pii_and_consent():
    assert [s.type for s in HI.find_pii("PAN ABCPE1234F aur number +91 98765 43210 hai")] == [
        "pan",
        "phone",
    ]
    assert HI.resolved("call_recording_consent") == "notice_required"
    assert HI.resolved("formats").date_order == "DMY"
    assert HI.all_languages() == {"hi-Latn", "hi", "en-IN", "en"}


def test_recipe_support_is_honest():
    assert HI.recipe_support["lfm25-audio"] == "understand_only"
    assert HI.recipe_support["cascade"] == "native"
    assert HI.recipe_support["qwen-omni"] == "unsupported"
