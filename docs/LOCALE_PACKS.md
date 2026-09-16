# Locale packs

The pipeline is language-agnostic. A **locale pack** is the one place where everything language- or market-specific lives, so adding a market never touches core, recipes, eval, or serve.

## What a pack contains

```python
class LocalePack(Protocol):
    id: str                          # BCP-47 with region: "en-US", "en-GB", "en-IN", "hi-Latn-IN", "zh-CN"
    languages: list[str]             # tags this pack handles, e.g. ["en"], ["hi-Latn", "hi", "en-IN"]
    parent: str | None               # "en" for en-US/en-GB/en-IN; shared rules inherit

    # --- text ---
    def detect_lang(self, text: str) -> str: ...            # per-turn tag incl. script (hi vs hi-Latn)
    def normalize_text(self, text: str) -> str: ...         # for WER: numbers, currency, dates, case, punctuation
    def transliterate(self, text: str, to_script: str) -> str: ...   # optional, e.g. Devanagari <-> Roman

    # --- entities & formats ---
    entity_types: list[EntityType]   # currency, date, phone, postal_code, national_id, address, person_name …
    formats: LocaleFormats           # currency symbols/words ("$", "£", "₹", "lakh", "crore", "万"),
                                     # date order (MDY/DMY/YMD), phone regexes, postal-code regex, address grammar

    # --- privacy ---
    pii_patterns: list[PIIPattern]   # SSN, NI number, Aadhaar, PAN, resident ID, IBAN, card, phone, email …
    privacy_notes: PrivacyNotes      # short region text shown by `prepare` (not legal advice) + links
    call_recording_consent: str      # "one_party" | "all_party" | "varies_by_state" | "notice_required"

    # --- synth ---
    name_generator: NameGenerator    # culturally plausible fake names, addresses, IDs
    scenario_templates: Path         # locale-flavoured versions of the base scenarios
    tts_defaults: list[str]          # preferred open TTS engines/voices for this locale
    stt_defaults: list[str]          # preferred STT for transcription in `prepare`

    # --- models ---
    recipe_support: dict[str, RecipeSupport]   # per recipe: "native" | "understand_only" | "cascade" | "unsupported"

    # --- eval ---
    benchmark: BenchmarkSpec         # vakforge-bench-<id>-v0 composition
```

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

## Adding a locale pack (checklist)

1. `vakforge/locales/<id>/` implementing `LocalePack`; inherit from a parent where sensible.
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
