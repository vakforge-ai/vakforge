# Evaluation

The point of vakforge is not "we fine-tuned it" but "we can show it got better on *your* held-out data." `vakforge eval` always runs the **base model and the tuned model on the same test split** and emits one report. No metric is reported without its baseline.

## Test split rules

- Held out by conversation **and** speaker; never seen by `train` or `synth` prompt examples.
- Stratified by `locale`, `audio.condition` (clean / phone / noisy), `language.primary`, and `meta.source` (real / synthetic). Report breaks down by each, so a multi-locale dataset cannot hide a weak language behind a strong one.
- Minimum 100 turns for any headline number; fewer → report shows the number with a "low-n" badge and a bootstrap CI.

## Metrics

### Recognition (all recipes; measured on the model's transcript or its internal text stream)

| Metric | How |
|---|---|
| WER / CER | `jiwer`, after the locale pack's normalizer (case, punctuation, numbers, currency, dates; script transliteration where the reference is in another script, e.g. Roman Hindi). CER is the headline for `zh-CN` and `ja`. Report both raw and normalized. |
| Entity accuracy | Exact match on `entities[]` by type as declared by the locale pack: `customer_id`, `phone`, `amount` (with currency), `date`, `person_name`, `address`, `postal_code`, `order_id`. This is usually the number that decides whether a business agent is usable. |
| Code-switch WER | WER restricted to turns with `lang_mix` length > 1. |

### Behaviour (all recipes)

| Metric | How |
|---|---|
| Tool-call accuracy | Per class: `tool_match` (right tool + valid args), `tool_miss` (correct refusal when tool absent), `non_tool` (no spurious call), `tool_result_speak` (narrates injected result correctly). Args scored by JSON-schema validation + exact match on required fields. |
| Task completion | Scripted multi-turn scenarios with a checklist (verified customer? booked? confirmed amount?). Scored by rules where possible, else an LLM judge with the rubric in `eval/judge_rubrics/`. Judge model and prompt hash recorded in the report. |
| Hallucination rate | Given the tools' returned facts, does the spoken answer contradict or invent? LLM judge with rubric; sampled human check on 30 items per run. |
| Instruction adherence | Persona/system-prompt constraints (language choice, greeting, no disallowed promises). Rubric judge. |

### Speech quality (recipes that emit audio)

| Metric | How |
|---|---|
| Intelligibility | ASR round-trip: transcribe the generated audio with a fixed reference ASR, WER vs the model's own text. |
| Voice similarity | Cosine similarity of speaker embeddings (e.g., ECAPA/WavLM-based) between generated audio and the target voice reference. Only when a voice target exists. |
| Naturalness (optional) | Small MOS-style listening test tooling: export 20 paired clips, collect 1–5 ratings via a simple local web page. Never claim MOS without listeners. |

### Latency (all recipes; measured on the serving path, not the training loop)

| Metric | How |
|---|---|
| TTFT / TTFA | Time from end of user speech to first text token / first audio chunk. p50 and p95. |
| Total response time | End of user speech to end of agent audio. |
| Real-time factor | Generated audio seconds / wall seconds. |
| Hardware | GPU/CPU model, quantization, batch size — all recorded. |

### Duplex (Recipe B only)

| Metric | How |
|---|---|
| Barge-in stop time | User starts speaking over the agent → agent audio energy drops below threshold. p50/p95. |
| Interruption response time | User finishes the interrupting utterance → agent's first relevant response. |
| False-interruption rate | Agent stops for backchannels ("hmm", "haan") that should not interrupt. |
| Overlap rate | Fraction of time with both streams active, compared to the human reference distribution. |

### Robustness

Every metric above re-run on augmented copies of the test split: phone band-pass, +10/+20 dB SNR babble, reverb. The report shows degradation, not just clean numbers.

## Report format

`runs/<ts>/report.md` (human) and `report.json` (machine). Sections, in order:

1. **Summary table** — each headline metric: base → tuned, delta, CI, n.
2. **Where it got better / worse** — top 5 improvements and top 5 regressions by slice.
3. **Breakdowns** — by locale, condition, language, source, entity type, tool class.
4. **Latency** — table + hardware.
5. **Samples** — 10 paired examples (user text, base answer, tuned answer, reference) with links to audio.
6. **Provenance** — manifest hash, config, versions, judge model/prompt hashes, seed.

`report.json` schema is in `eval/report_schema.json` so benchmarks across recipes are comparable.

## Public benchmarks — `vakforge-bench-<locale>-v0`

One small, consented, versioned benchmark per locale pack, with the same shape so recipes and locales are comparable:

- ~300–600 turns in the pack's languages (for `hi-Latn-IN`: Hinglish with Roman-Hindi transcripts plus a Devanagari subset; for `en`: a mix of US, UK, Indian English accents).
- Dense in the pack's entities: local names, city/street addresses, postal codes, currency amounts in local phrasing (`$1,200`, `£45`, `₹2 lakh`, `3万元`), local date formats, phone-like IDs (synthetic).
- Tool-calling scenarios: booking, status check, ticket creation, transfer to human, plus no-tool chitchat.
- Conditions: clean, phone-band, noisy; a duplex subset with scripted interruptions and backchannels.
- Sources: synthetic (rendered with open TTS) + a small real, consented set recorded under `DATA_ETHICS.md` rules.

Launch: `vakforge-bench-en-v0`, `vakforge-bench-hi-latn-v0`. Then `zh-v0` with the `qwen-omni` recipe. Every recipe's `report.json` on each benchmark is committed under `benchmarks/` and summarized in `README.md`.
