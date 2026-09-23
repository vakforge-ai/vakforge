# Data ethics — consent, PII, licences

Real customer calls are the most valuable training data for this project and the easiest way to get someone hurt or sued.

> **What is enforced today:** the canonical schema (`vakforge validate`) rejects a record whose consent or redaction claim has nothing behind it — see [the provenance rules](DATA_FORMAT.md). The locale packs carry the PII patterns and each region's consent rule, and `vakforge locales <id>` prints them.
>
> Everything below describing `prepare` is a **specification**, not shipped code. `prepare` is generated per project by the agent skill, and this file is the contract it has to meet. Present tense means "must", not "does".

## Consent

- Every canonical record carries `meta.consent` ∈ `recorded_verbal | written | synthetic | public_license | none`.
- `prepare` asks for the consent basis once per source directory and a reference (`consent_ref`: policy name/version, or the notice played at call start).
- `none` is only written with `--allow-unconsented`, is excluded from every export, benchmark, notebook, and published checkpoint, and produces a warning on every run that touches it.
- Voice is biometric data in many jurisdictions. If you clone a real person's voice, keep a written consent record for that specific use and name the person in `meta.voice_consent_ref`.
- Applicable law depends on where the data subjects are. Each locale pack ships a short `privacy_notes` block that `prepare` prints, plus a `call_recording_consent` flag. Starting points (not legal advice; confirm with counsel before training on real customer data):
  - **USA** — no single federal privacy law; state laws apply (e.g. California CCPA/CPRA). Illinois' BIPA treats voiceprints as biometric identifiers and has driven voice-related litigation. Call-recording consent varies by state: some are one-party, several (including California) require all parties.
  - **UK** — UK GDPR + Data Protection Act 2018; recording and processing calls needs a lawful basis and notice; ICO guidance applies. Voice used for identification is special-category (biometric) data.
  - **EU** — GDPR; same biometric special-category treatment (Art. 9); DPIA likely required for voice-agent training on customer calls.
  - **India** — Digital Personal Data Protection Act, 2023 and its rules; notice and consent for processing.
  - **China** — Personal Information Protection Law (PIPL); separate consent for sensitive personal information (biometrics), data-localisation and cross-border transfer rules; generative-AI service regulations may apply to deployment.

## PII

`prepare` runs a redaction pass **before** anything is written to `data/` or a manifest:

1. **Pattern detection** — shared patterns (email, card numbers via Luhn, IBAN) plus the locale pack's `pii_patterns`: phone formats (+1/+44/+91/+86 …), national IDs (SSN, NI number, Aadhaar, PAN, Chinese resident ID), bank tokens (routing/IFSC/sort codes), vehicle plates, postal codes when combined with a street address.
2. **NER** — person names, organisations, locations via a small multilingual NER model; locale name lists (e.g. Roman-Hindi names) as a fallback. Conservative default: redact anything the NER flags with confidence above a low threshold; the cost of over-redaction is much lower than under-redaction.
3. **Audio redaction** — for each redacted span with timestamps, replace the audio segment with a tone or silence (configurable) so training audio never contains the PII even if the transcript is fixed.
4. **Redaction log** — `redactions/<id>.json` lists each span, type, method, and replacement token (e.g., `<PHONE_1>`), so downstream eval can still score "did the model handle a phone number here" without knowing the number.
5. **Keep-list** — business entities you *want* the model to learn (your product names, branch names, your own support number) go in `configs/keep_list.yaml` and are never redacted.

Placeholders are consistent within a conversation (`<PERSON_1>` refers to the same person throughout) so dialogue structure survives.

`--skip-redaction` exists for already-redacted or synthetic data; it logs a warning on every use and sets `meta.pii_redacted=false` unless `--already-redacted` is passed with a reason.

## Synthetic data

- Synthetic dialogues must not contain real customer facts. Scenario templates use generated names, IDs, and addresses.
- Rendered voices come from open TTS models under licences that permit this use; do not clone real voices for synthetic data unless consented as above.
- `meta.source = "synthetic"` always; eval reports separate synthetic from real performance so we never claim real-world gains from synthetic tests alone.

## Model and dataset licences

- Every recipe has `LICENSE_NOTES.md` summarising the base model's licence, commercial-use status, attribution requirements, and gating steps. `vakforge train` prints the relevant note and requires `--accept-license` (or config equivalent) the first time.
- Public datasets (Vistaar, IndicVoices, Common Voice, etc.) are used per their terms; the manifest records `meta.license` per row so a mixed dataset can be filtered by licence before publishing anything derived from it.
- We publish benchmarks and demo datasets only from synthetic or explicitly consented, licence-clear rows.

## Security of local data

- `data/raw/` and `runs/*/checkpoint/` are git-ignored by default; `vakforge init` writes the `.gitignore`.
- No telemetry. The CLI never sends data anywhere unless a step explicitly uses an external API (LLM for `synth`, if configured), and it says so before doing it.
- Checkpoints trained on real data are treated as containing that data. Do not upload them publicly without a membership-inference sanity check and the same consent basis as the data.

## Model behaviour

- The agent must identify itself as automated when asked, and by default at the start of the call. This is a system-prompt default in `init` and a rubric item in eval.
- Training data should include refusal/hand-off examples (transfer to human, cannot do X) so fine-tuning does not erode them.
