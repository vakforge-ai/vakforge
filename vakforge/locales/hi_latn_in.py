"""hi-Latn-IN: Hinglish. Roman-script Hindi mixed with English, plus Devanagari turns.

ASR language IDs are unreliable on code-switched speech, so `prepare` tags each turn with
`detect_lang` here: Devanagari script means `hi`; Roman text dense in Hindi function words
means `hi-Latn`; everything else is `en-IN`. Inherits Indian IDs and rupee handling from
en-IN.
"""

from __future__ import annotations

import re
import unicodedata

from vakforge.locales.base import register
from vakforge.locales.en_in import _AMOUNT, _INDIAN_GROUPING, EnIN

# Frequent Roman-Hindi words. Deliberately excludes spellings that are also common English
# words (do, main, the, to, he, me, par, hi, ho, man) so English turns stay English.
ROMAN_HINDI = frozenset(
    """
    hai hain hoon hun tha thi hoga hogi honge ka ki ke ko se mein mai mera meri mere tera
    teri tere hamara hamari apna apni apne aap aapka aapki aapko tum tumhe tumhara mujhe
    humko hume unko usko isko inko kya kaise kyun kyon kab kahan kaun kitna kitni kitne
    nahi nahin nai haan han ji theek thik accha acha achha bilkul zaroor aur ya lekin
    magar bhi sirf phir abhi kal aaj parso pehle baad jaldi thoda thodi bahut zyada jyada
    kam sab kuch koi ek kar karo karna karein kijiye karunga karenge kiya kiye raha rahi
    rahe rha rhi sakta sakti sakte chahiye batao bataiye bolo bol boliye dekho dekhiye
    suno suniye wala wali wale waala liye yeh ye woh wo yahan wahan namaste namaskar
    dhanyavaad dhanyawad shukriya bhai didi bhaiya paisa paise rupaye din mahina saal
    ghar dukaan
    nhi krna kro krke dedo dena deke lena lekar milega milegi milta chahta chahti chahte
    samajh samjha pata malum mujhko tumko wapas wapis chalu chalta dikkat turant kyunki
    matlab bataye hua hui gaya gayi rakho bhejo bhej aayega aayegi aaya aayi
    """.split()  # noqa: SIM905  (a word list reads better as one string)
)

# Spelling variants folded to one form so WER does not punish transliteration choices.
VARIANTS = {
    "nahin": "nahi",
    "nai": "nahi",
    "han": "haan",
    "thik": "theek",
    "acha": "accha",
    "achha": "accha",
    "kyon": "kyun",
    "mai": "main",
    "hun": "hoon",
    "jyada": "zyada",
    "dhanyawad": "dhanyavaad",
    "rha": "raha",
    "rhi": "rahi",
    "waala": "wala",
}

# Devanagari Unicode block, U+0900 to U+097F.
_DEVANAGARI = re.compile("[ऀ-ॿ]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_PERCENT = re.compile(r"(?<=\d)\s?%")


def _strip_punctuation(text: str) -> str:
    """Drop Unicode punctuation and symbols but keep Devanagari vowel signs and decimals."""
    out = []
    for i, ch in enumerate(text):
        if unicodedata.category(ch)[0] in "PS":
            is_decimal = (
                ch == "."
                and 0 < i < len(text) - 1
                and text[i - 1].isdigit()
                and text[i + 1].isdigit()
            )
            out.append(ch if is_decimal else " ")
        else:
            out.append(ch)
    return "".join(out)


@register
class HiLatnIN(EnIN):
    id = "hi-Latn-IN"
    name = "Hinglish"
    languages = ["hi-Latn", "hi"]
    parent = "en-IN"
    # Formats, PII patterns, consent and privacy notes come from en-IN.
    formats = None
    pii_patterns = []
    call_recording_consent = None
    privacy_notes = None
    recipe_support = {
        "lfm25-audio": "understand_only",  # English speech out; Hinglish input after fine-tune
        "moshi-lora": "understand_only",
        "qwen-omni": "unsupported",  # TODO(verify): measure Hindi speech output before marking
        "cascade": "native",  # IndicConformer + Indic Parler-TTS / IndicF5
    }

    def _hindi_ratio(self, text: str) -> tuple[int, int]:
        words = [w.lower() for w in _LATIN_WORD.findall(text)]
        hits = sum(1 for w in words if w in ROMAN_HINDI)
        return hits, len(words)

    def detect_lang(self, text: str) -> str:
        """`hi` for mostly Devanagari, `hi-Latn` for Roman Hindi, otherwise `en-IN`.

        One fifth of the words is enough, because the word list excludes spellings that are
        also English. A single Hindi verb in an otherwise English sentence ("order cancel kar
        do") still means the caller is speaking Hinglish. This is a heuristic, not a trained
        classifier: see docs/RESEARCH.md on per-turn language identification.
        """
        deva = len(_DEVANAGARI.findall(text))
        latin = sum(len(w) for w in _LATIN_WORD.findall(text))
        if deva and deva >= latin:
            return "hi"
        hits, words = self._hindi_ratio(text)
        if hits and hits / words >= 0.2:
            return "hi-Latn"
        return "en-IN"

    def lang_mix(self, text: str) -> list[str]:
        """Every language present in a turn, primary first, for `turns[].lang_mix`."""
        primary = self.detect_lang(text)
        present = [primary]
        hits, words = self._hindi_ratio(text)
        if _DEVANAGARI.search(text) and "hi" not in present:
            present.append("hi")
        if hits and "hi-Latn" not in present:
            present.append("hi-Latn")
        if words - hits > 0 and primary != "en-IN":
            present.append("en-IN")
        return present

    def normalize_text(self, text: str) -> str:
        """Rupee amounts, Devanagari digits, spelling variants; keeps Devanagari intact."""
        t = _INDIAN_GROUPING.sub("", text.translate(_DEVANAGARI_DIGITS))
        t = _AMOUNT.sub(lambda m: f"{m.group(1)}{m.group(2) or ''} rupees", t)
        t = _PERCENT.sub(" percent", t.lower()).replace("&", " and ")
        words = _strip_punctuation(t).split()
        return " ".join(VARIANTS.get(w, w) for w in words)
