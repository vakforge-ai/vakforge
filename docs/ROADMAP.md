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
- [x] Golden tests for every pack (normalizer, detect_lang, PII positive/negative)
- [x] `vakforge locales` to list packs and show resolved settings
- [x] `inspect`: classify a data folder into documents, tables, chats, audio; per-file errors recorded, never fatal
- [x] `inspect` for text and tables: words, languages and PII via the locale pack; CSV/TSV/JSON/SQL columns, id columns, tool candidates; JSONL and WhatsApp chat exports
- [x] `inspect` for audio: duration, sample rate, channels, clipping, silence, condition guess (no SNR or spoken-language guess: those need ASR, out of core scope)
- [x] `inspect.json` report for `recommend` and the agent skill
- [ ] `inspect`: PDF / DOCX / XLSX text (listed as unreadable with a hint today)
- [x] `recommend`: rules from `DECISION_GUIDE.md` as code; reads `inspect.json` or a folder; routes per source, fine-tune verdict, recipe filtered by locale `recipe_support` and GPU, data gap, consent checklist; writes `recommend.json`
- [ ] `recommend`: interactive questionnaire (flags `--goal`, `--gpu`, `--duplex` cover it non-interactively today)

## Phase 2 — Agent skill
- [x] `skill/vakforge/SKILL.md`: hard rules plus the eight-step workflow with a completion criterion per step
- [x] `skill/vakforge/references/`: decision rules, data format, data safety, recipes with verify-first checklist, eval and serving, locale hooks
- [x] Skill calls the core CLI for init, locales, inspect, recommend and validate; generates recipe glue per project
- [x] Consistency test: frontmatter, referenced files, CLI commands named in the skill exist
- [ ] Tested on one real project end to end (documents + tables, no audio) and one with call recordings

## Phase 3 — Landing page
- [x] `site/` static landing page (Cloudflare Pages): hero demo, pipeline, data router, repo parts, locale explorer, eval report, redaction console, agent skill, CTA
- [x] Mobile and tablet pass (390 / 768 / 1024 px, no horizontal overflow)
- [x] Deploy to Cloudflare Pages: https://vakforge.pages.dev, auto-deploys from main
- [x] Brand assets: mark, favicons, app icon, social and OG images under `site/assets/` (originals stay local in `assets-src/`)
- [ ] Light theme for the landing page (toggle + `prefers-color-scheme`), reusing the light diagram set
- [ ] Site copy audit before going public: label evaluation report, redaction console and serve as planned until they exist

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
