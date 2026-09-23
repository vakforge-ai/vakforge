# Roadmap

Single source of truth for status. Update checkboxes in the same commit as the work. "Done" means: tests pass on CPU, docs updated, verified against upstream source where an upstream is involved.

Shape of v0: a zero-ML-dep core library, an agent skill that carries the knowledge, and a landing page. Recipes that need a GPU come after, largely from contributors who have one.

## Phase 0 — Core scaffold
- [x] `pyproject.toml` with core deps; recipe extras declared but empty until each recipe pins its upstream
- [x] `uv.lock`, `.gitignore`, `LICENSE` (Apache-2.0), `Makefile`
- [x] Package layout (only what Phase 0 needs), `locales/` with `LocalePack` base + registry + `en`, `en-US`, `en-GB`, `en-IN` skeletons
- [x] `vakforge --version`, `vakforge init --locale` (writes `vakforge.yaml`, data dirs, `.gitignore`)
- [x] `schema.py` (pydantic v2, incl. `locale`; audio optional for text-sourced records) + `vakforge schema` JSON Schema export
- [x] `vakforge validate`: schema, audio file vs declaration, locale/lang registry, tool args vs JSON Schema, consent, `splits.json`
- [x] Schema fails closed on provenance: consent needs its reference or licence, real data needs redaction plus a log, real recordings need `voice_consent_ref`, entity offsets must match the text they point at, `audio.path` cannot escape the dataset, duplicate tool names and same-speaker stereo maps rejected
- [x] `validate` proves the redaction claim instead of trusting it: rescans text, tool arguments and tool results with the locale pack, requires the named `redaction_log` to exist and parse, and reports a leak by type and offset without repeating the value
- [x] Generated test fixtures (WAVs synthesized in `tests/conftest.py`)
- [x] GitHub Actions: ruff + pytest, Python 3.11/3.12

## Phase 1 — Locale packs · Inspect · Recommend
- [x] Pack model: formats, PII patterns with checksum validators, consent, privacy notes, recipe support, inheritance
- [x] Pack `en` (parent): English WER normalizer, email / card (Luhn) / IBAN (mod-97) patterns
- [ ] Pack `en` (parent): NER for names and addresses, base scenarios
- [x] Pack `en-US`: dollars, MDY, SSN, NANP phones, state consent notes
- [x] Pack `en-GB`: pounds, DMY, NI number, UK phones, UK GDPR notes
- [x] Pack `en-IN`: rupees with lakh/crore and Indian digit grouping, Aadhaar (Verhoeff), PAN, +91 mobiles, DPDP notes
- [x] Pack `hi-Latn-IN`: Roman-Hindi vs English vs Devanagari detection, `lang_mix`, Devanagari-safe normalizer with spelling variants
- [ ] Pack `hi-Latn-IN`: Devanagari to Roman transliteration, Indian name/address generator
- [x] PII patterns survive real transcripts: case-insensitive NI number and PAN (ASR output is lowercase), compact SSN behind a cue word, reference numbers not mistaken for Indian mobiles, IBAN country registry so invented countries fail
- [x] Golden tests for every pack (normalizer, detect_lang, PII positive/negative)
- [x] `vakforge locales` to list packs and show resolved settings
- [x] `inspect`: classify a data folder into documents, tables, chats, audio; per-file errors recorded, never fatal
- [x] `inspect` for text and tables: words, languages and PII via the locale pack; CSV/TSV/JSON/SQL columns, id columns, tool candidates; JSONL and WhatsApp chat exports
- [x] `inspect` for audio: duration, sample rate, channels, narrowband, clipping, silence — measurements only, no condition or spoken-language verdict (those need ASR, and continuous energy is as much dense speech as it is noise)
- [x] `inspect.json` report for `recommend` and the agent skill, with discovered and profiled counts kept separate so totals say how much of the folder they cover
- [x] `inspect`: files too large to parse whole are skipped with that as the reason, and partial reads are flagged `truncated` rather than reported as totals
- [x] `inspect` parsers survive real exports: bracketed (iOS) WhatsApp speakers, schema-qualified SQL tables, per-line JSONL errors instead of losing the file, CSV counted without loading every row
- [ ] `inspect`: PDF / DOCX / XLSX text (listed as unreadable with a hint today)
- [x] `recommend`: rules from `DECISION_GUIDE.md` as code; reads `inspect.json` or a folder; routes per source, fine-tune verdict, recipe filtered by locale `recipe_support` and GPU, data gap, consent checklist; writes `recommend.json`
- [x] `recommend`: per-goal bars with their own unit, floor, target, confidence label and citation (`BARS`); three-state verdict (`blocked` / `baseline_first` / `candidate`) instead of a boolean, per `docs/RESEARCH.md`
- [x] `recommend` counts usable evidence only: raw audio is never converted into conversation turns, goals are inferred from profiled files rather than discovered ones, and evidence whose fitness is unproven cannot reach `candidate`
- [x] `recommend`: a decision per goal (`goal_decisions[]`) — own unit, bar, evidence, recipe and blockers — with the project verdict as the roll-up; naming a duplex base model is separated from whether the data can adapt it
- [ ] `recommend`: interactive questionnaire (flags `--goal`, `--gpu`, `--duplex` cover it non-interactively today)

## Phase 2 — Agent skill
- [x] `skill/vakforge/SKILL.md`: hard rules plus the eight-step workflow with a completion criterion per step
- [x] `skill/vakforge/references/`: decision rules, data format, data safety, recipes with verify-first checklist, eval and serving, locale hooks
- [x] Skill calls the core CLI for init, locales, inspect, recommend and validate; generates recipe glue per project
- [x] Consistency test: frontmatter, referenced files, CLI commands named in the skill exist
- [x] `examples/hinglish-shop`: synthetic documents + tables + chat project with `inspect.json` and `recommend.json` committed and diffed by a test on every run
- [ ] Tested on one real project end to end (documents + tables, no audio) and one with call recordings

## Phase 3 — Landing page
- [x] `site/` static landing page (Cloudflare Pages): hero demo, pipeline, data router, repo parts, locale explorer, eval report, redaction console, agent skill, CTA
- [x] Mobile and tablet pass (390 / 768 / 1024 px, no horizontal overflow)
- [x] Deploy to Cloudflare Pages: https://vakforge.pages.dev, auto-deploys from main
- [x] Brand assets: mark, favicons, app icon, social and OG images under `site/assets/` (originals stay local in `assets-src/`)
- [x] Light theme for the landing page: `prefers-color-scheme` default, nav toggle saved per browser and applied before first paint (the site embeds no diagrams, so none to swap)
- [x] Site copy audit: every step labelled `in the CLI` or `skill generates`, example report and hero run marked illustrative, routing matches `docs/RESEARCH.md`, evidence linked from the data router

## Phase 4 — Prepare · Synth
- [ ] `prepare`: ingest documents, tables, chat logs into canonical facts / tool definitions / conversations
- [ ] `prepare`: audio path: normalize (24 kHz), channels, transcription (faster-whisper; pack override), diarization (pyannote optional)
- [ ] `prepare`: per-turn language tagging, PII redaction with logs and keep-list, consent metadata, leak-free splits
- [ ] `synth`: scenario templates + locale variants; provider-agnostic LLM dialogue generator with tool calls and chitchat class
- [ ] `synth`: TTS rendering via pack defaults, stereo mixing, augmentation
- [ ] Public demo datasets: `en-US` (~200 turns), `hi-Latn-IN` (~200 turns)

## Phase 5 — Recipe A: `lfm25-audio` · Eval · Serve
- [ ] Verify `liquid_audio` API against pinned version; `UPSTREAM_NOTES.md`
- [ ] Adapter, `train`, eval metrics, `report.md`/`report.json` base vs tuned
- [ ] Colab notebook end to end on `en-US` demo; second run on `hi-Latn-IN`
- [ ] `serve` backend/protocol split; OpenAI Realtime WebSocket front end (documented event subset), Python client, Pipecat and LiveKit examples, Dockerfile

## Phase 6 — More protocol front ends
- [ ] WebRTC front end via LiveKit or Pipecat transports
- [ ] SIP / telephony front end
- [ ] Plain HTTP one-turn front end
- [ ] Gemini Live format (on request)

## Phase 6b — More recipes (contributor-friendly)
- [ ] Recipe B `moshi-lora`: adapter, train wrapper, duplex eval, serve path
- [ ] Recipe D `qwen-omni` + pack `zh-CN`
- [ ] Recipe C `cascade`

## Phase 7 — Benchmarks
- [ ] `vakforge-bench-en-v0`, `vakforge-bench-hi-latn-v0`, later `zh-v0`
- [ ] Results per recipe per locale under `benchmarks/`; README results table; one-command reproduction

## Later / ideas (not committed)
- Packs `es`, `de`, `fr`, `pt-BR`, `ja`, `ar`
- Web demo (browser client to `serve`)
- Telephony (SIP) example
- Hosted version
