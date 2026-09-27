# Data safety: consent, redaction, licences

These are enforced in the code you write for `prepare`, not just documented. Full text:
`docs/DATA_ETHICS.md`.

## Consent

- `prepare` asks for the consent basis once per source folder and a `consent_ref` (policy name and version, or the notice played at call start). Every row carries `meta.consent`.
- A recording is not automatically biometric data: a voice becomes special-category under UK GDPR when it is processed *to identify someone*, and Illinois BIPA treats voiceprints as biometric identifiers. Set `meta.allowed_uses` to what the row is actually for. Cloning a real person's voice needs `voice_clone` plus a written consent record in `meta.voice_consent_ref`, and the schema rejects one without the other.
- Print the locale pack's `privacy_notes` and `call_recording_consent` rule to the user before touching recordings (`vakforge locales <id>`). They are starting points, not legal advice:

| Region | Starting point |
|---|---|
| USA | no single federal law; state laws (California CCPA/CPRA); Illinois BIPA treats voiceprints as biometric; call-recording consent varies by state, some require all parties |
| UK | UK GDPR and DPA 2018; lawful basis and notice; voice used for identification is special-category data; ICO guidance |
| EU | GDPR; biometric is special-category (Art. 9); a DPIA is likely required |
| India | Digital Personal Data Protection Act 2023 and rules; notice and consent; Aadhaar numbers never stored or shown in full |
| China | PIPL; separate consent for biometrics; data localisation and cross-border rules |

## Redaction, before anything is written to `data/`

1. Pattern detection: shared patterns (email, cards by Luhn, IBAN) plus the pack's `pii_patterns` (phones, national IDs with checksums, postal codes when next to a street address). `pack.find_pii(text)` returns non-overlapping spans.
2. NER for person names, organisations, locations with a small multilingual model; redact anything above a low confidence threshold. Over-redaction is cheap; under-redaction is not.
3. Audio: replace each redacted span's audio with a tone or silence so training audio never carries the PII even if the transcript is later fixed.
4. Log every span to `redactions/<id>.json` so eval can still ask "did the model handle a phone number here". `vakforge validate` rejects a log that cannot be checked, so write exactly this shape: top-level `conversation_id` (the record's `id`) and `spans`; each span with `type`, `placeholder` (the text you actually left behind), `field` (`text`, `system_prompt`, `tool_call.arguments` or `tool_result.content`) and `turn` (omit it only for `system_prompt`); for audio, `{"start_s", "end_s", "method": "tone" | "silence" | "noise"}` inside the recording. The placeholder must appear in that field of that turn, or the span fails as describing a redaction that did not happen. Keep the log inside the dataset directory; a path or symlink that leaves it is rejected.
5. Keep-list: the user's own product names, branch names and support number go in `configs/keep_list.yaml` and are never redacted.

Placeholders stay consistent within a conversation: `<PERSON_1>` is the same person
throughout, so dialogue structure survives.

Flags: `--skip-redaction` for already-redacted or synthetic data logs a warning on every use
and sets `pii_redacted=false` unless `--already-redacted <reason>` is given.

## Synthetic data

No real customer facts in scenario templates. Names, IDs and addresses come from the pack's
generators. Voices come from open TTS under licences that allow it. `meta.source =
"synthetic"` always, so eval never reports synthetic gains as real-world gains.

## Licences and publishing

- Every recipe carries a `LICENSE_NOTES.md` for its base model; `train` prints it and requires `--accept-license` the first time.
- `meta.license` per row lets a mixed dataset be filtered by licence before publishing anything derived from it.
- Checkpoints trained on real data are treated as containing that data: no public upload without a membership-inference sanity check and the same consent basis as the data.
- `data/` (raw exports, recordings, prepared datasets and redaction logs), `runs/` and audio files stay git-ignored; `vakforge init` writes that `.gitignore`.
- No telemetry. The only network calls are the ones the user configured for synth, announced before they happen.

## Behaviour defaults

The assistant identifies itself as automated when asked, and by default at the start of a
call. Training data includes refusal and hand-off examples so fine-tuning does not erode them.
