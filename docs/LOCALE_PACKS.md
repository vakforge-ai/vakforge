# Locale packs

The pipeline is language-agnostic. A **locale pack** is the one place where everything language- or market-specific lives, so adding a market never touches core, recipes, eval, or serve.

> **Status:** packs are built and tested — `en`, `en-US`, `en-GB`, `en-IN` and `hi-Latn-IN` ship today, with golden tests for every normalizer, language detector and PII pattern. Run `vakforge locales` to list them and `vakforge locales <id>` to see one pack's resolved settings. The sections on `synth` and benchmark composition are specification.

## What a pack contains

This is the whole of `LocalePack` as it exists today (`vakforge/locales/base.py`):

```python
class LocalePack:
    id: ClassVar[str]                    # BCP-47 with region: "en-US", "en-GB", "en-IN", "hi-Latn-IN"
    name: ClassVar[str]                  # human-readable, e.g. "Hinglish"
    languages: ClassVar[list[str]]       # tags this pack handles, e.g. ["hi-Latn", "hi"]
    parent: ClassVar[str | None]         # "en" for en-US/en-GB/en-IN; shared rules inherit

    formats: ClassVar[LocaleFormats | None]          # currency symbols and words, date order, examples
    pii_patterns: ClassVar[list[PIIPattern]]         # regex + optional checksum + context rules
    call_recording_consent: ClassVar[Consent | None] # one_party | all_party | varies_by_state | notice_required
    privacy_notes: ClassVar[PrivacyNotes | None]     # short sourced region text (not legal advice) + links
    recipe_support: ClassVar[dict[str, Support]]     # native | understand_only | cascade | unsupported

    # inheritance
    def parent_pack(self) -> LocalePack | None: ...
    def all_languages(self) -> set[str]: ...                 # own tags plus the parent chain's
    def all_pii_patterns(self) -> list[PIIPattern]: ...       # own first, parent's unless overridden by name
    def resolved(self, attr: str): ...                        # nearest pack up the chain that sets it

    # text hooks packs override
    def detect_lang(self, text: str) -> str: ...              # per-turn tag incl. script (hi vs hi-Latn)
    def lang_mix(self, text: str) -> list[str]: ...           # every language in the turn, primary first
    def normalize_text(self, text: str) -> str: ...           # for WER: numbers, currency, case, punctuation
    def find_pii(self, text: str) -> list[PIISpan]: ...       # non-overlapping spans, longest kept
```

Planned, once the stages that need them exist: `transliterate` (Devanagari ↔ Roman), an entity-type list,
a name and address generator for `synth`, TTS and STT defaults, and a benchmark spec. None of these are
in the class yet; `docs/ROADMAP.md` tracks them.

`vakforge init --locale <id>` writes the pack id into the project config; every stage reads it. A project can list several locales (e.g. `["en-IN", "hi-Latn-IN"]`) for mixed data; turns still carry their own `lang`.

## Packs

### `en` (parent) with `en-US`, `en-GB`, `en-IN` — launch

Shared: English normalizer, person/organisation NER, email/card/IBAN patterns, tool-call scenarios.

| | en-US | en-GB | en-IN |
|---|---|---|---|
| Currency | `$`, "dollars", "bucks", "grand" | `£`, "pounds", "quid" | `₹`, "rupees", "lakh", "crore" |
| Dates | MDY | DMY | DMY |
| Phone | NANP 10-digit, +1 | +44, 07… mobiles | +91, 10-digit starting 6–9 |
| Postal | ZIP / ZIP+4 | postcode (alphanumeric) | 6-digit PIN |
| National ID patterns | SSN | NI number | Aadhaar (12 digits), PAN |
| Call-recording consent | varies by state (some all-party) | notice / lawful basis | notice; DPDP |
| Recipe support | all native | all native | all native (accent robustness via fine-tune) |

### `hi-Latn-IN` (Hinglish) — launch, showcase

- Detects Roman Hindi vs English per turn using a Hindi word-list + script heuristic (ASR language IDs are unreliable here).
- Normalizer handles ₹/lakh/crore, Indian date phrasing, mixed-script numbers; optional Devanagari↔Roman transliteration for WER against either reference.
- Name/address generators produce Indian names, city/street/PIN combos.
- Recipe support: `lfm25-audio` and `moshi-lora` = **understand_only** (English speech out; Hinglish input understood after fine-tune); `cascade` = native via IndicConformer + Indic Parler-TTS / IndicF5; `qwen-omni` = verify.
- Benchmark: `vakforge-bench-hi-latn-v0`.

### `zh-CN` — planned (first non-English)

- Recipe: `qwen-omni` (native Mandarin speech in/out, function calling) or `cascade` (Paraformer/Whisper + LLM + CosyVoice/Qwen3-TTS).
- Formats: ¥/元, 万/亿 number groups, YMD dates, +86 mobiles, 6-digit postal codes, 18-digit resident ID pattern.
- Privacy notes: PIPL, cross-border data-transfer rules, data localisation; models mirrored on ModelScope for users without Hugging Face access.
- Benchmark: `vakforge-bench-zh-v0`.

### `es` (es-ES / es-MX), `de`, `fr`, `pt-BR`, `ja`, `ar` — planned

Added in the order native speech-output support appears in open models; until then `cascade` with locale STT/TTS defaults.

## How packs are implemented

- One module per pack under `vakforge/locales/` (`en.py`, `en_us.py`, `en_gb.py`, `en_in.py`, `hi_latn_in.py`), imported by `vakforge/locales/__init__.py`, which registers them.
- A pack is a `LocalePack` subclass with class attributes (`formats`, `pii_patterns`, `call_recording_consent`, `privacy_notes`, `recipe_support`) plus optional overrides of `detect_lang` and `normalize_text`.
- Inheritance: `parent` names another pack. Language tags and PII patterns are merged up the chain (a child pattern with the same `name` replaces the parent's). Scalar settings resolve to the nearest pack that sets them: `pack.resolved("call_recording_consent")`.
- PII patterns are a regex plus an optional checksum validator (`vakforge/locales/checksums.py`: Luhn, Verhoeff, IBAN mod-97) so look-alike digit strings are not flagged. `pack.find_pii(text)` returns non-overlapping spans.
- Postal codes are not PII patterns on their own. A redaction step should only treat one as personal data next to a street address.
- Inspect any pack's resolved settings with `vakforge locales <id>`.

## Adding a locale pack (checklist)

1. `vakforge/locales/<id_with_underscores>.py` implementing `LocalePack`; inherit from a parent where sensible, and import it in `vakforge/locales/__init__.py`.
2. Unit tests: `detect_lang`, `normalize_text` (golden cases incl. numbers, currency, dates), every `pii_pattern` (positive and negative cases), name generator sanity.
3. Scenario templates localised (not just translated — local business norms, greetings, verification steps).
4. `tts_defaults` / `stt_defaults` verified to run; `recipe_support` filled honestly.
5. `privacy_notes` with sources; `call_recording_consent` set.
6. `benchmark` spec + at least a synthetic benchmark committed.
7. Row in `README.md` locale table; section here.

## Design rules

- Core never branches on a language string; it asks the pack.
- A pack may declare a recipe `unsupported`; `recommend` then routes around it instead of promising results.
- Eval reports always break down by `locale` and `lang`, so a multi-locale dataset cannot hide a weak language behind a strong one.
