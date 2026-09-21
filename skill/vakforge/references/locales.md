# Locale packs: what to ask the pack for

Everything language- or market-specific lives in a pack. Ask the CLI, never hard-code:

```bash
vakforge locales                 # id, name, parent, languages, consent rule, PII pattern count
vakforge locales hi-Latn-IN      # formats, PII types, consent, recipe support, privacy notes
```

In Python, for the glue you write:

```python
from vakforge.locales import get_pack

pack = get_pack("hi-Latn-IN")
pack.detect_lang(text)           # per-turn tag: "hi", "hi-Latn" or "en-IN"
pack.lang_mix(text)              # every language in a code-switched turn, primary first
pack.normalize_text(text)        # WER normalizer: currency words, digit grouping, spelling variants
pack.find_pii(text)              # non-overlapping spans with checksum-validated IDs
pack.resolved("call_recording_consent")   # walks the parent chain
pack.resolved("recipe_support")           # {"lfm25-audio": "understand_only", ...}
pack.resolved("privacy_notes").summary
```

## Shipped packs

| Pack | Inherits | Adds |
|---|---|---|
| `en` | | email, payment cards (Luhn), IBAN (mod-97); English WER normalizer |
| `en-US` | `en` | dollars, MDY dates, SSN (invalid ranges rejected), NANP phones; consent varies by state |
| `en-GB` | `en` | pounds, DMY, National Insurance number, UK phones; notice required, UK GDPR |
| `en-IN` | `en` | rupees with lakh/crore and Indian digit grouping, Aadhaar (Verhoeff), PAN, +91 mobiles; DPDP Act |
| `hi-Latn-IN` | `en-IN` | Roman-Hindi vs English vs Devanagari detection, `lang_mix`, Devanagari-safe normalizer with spelling variants; recipes: `lfm25-audio` and `moshi-lora` understand only, `cascade` native |

Support levels: `native` (speaks it), `understand_only` (understands input, speech output
stays English), `cascade` (via the pack's STT and TTS), `unsupported`.

## Adding a pack for a new market

One module `vakforge/locales/<id>.py` subclassing `LocalePack`, imported in
`vakforge/locales/__init__.py`. Set `formats`, `pii_patterns` (regex plus checksum where one
exists), `call_recording_consent`, `privacy_notes` with sources, `recipe_support` filled
honestly, and override `detect_lang` and `normalize_text` if the language needs it. Golden
tests for the normalizer, `detect_lang`, and every PII pattern with positive and negative
cases. Scenario templates localised, not just translated: local greetings, verification
steps, business norms.
