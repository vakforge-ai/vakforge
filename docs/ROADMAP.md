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
- [ ] Pack `en` (parent): normalizer, NER, shared PII patterns, base scenarios
- [ ] Pack `en-US`, `en-GB`, `en-IN`: formats, national-ID patterns, consent notes
- [ ] Pack `hi-Latn-IN`: Roman-Hindi detection, transliteration helpers, Indian name/address generator
- [ ] Golden tests for every pack (normalizer, detect_lang, PII positive/negative)
- [ ] `inspect` for audio: stats, clipping, silence, SNR, language guess
- [ ] `inspect` for text and tables: documents, chat exports, CSV/SQL schemas; entity and tool-candidate discovery
- [ ] `recommend`: questionnaire + rules from `DECISION_GUIDE.md`, honours `recipe_support`, says "retrieval, not fine-tune" when true

## Phase 2 — Agent skill
- [ ] `skill/vakforge/SKILL.md`: workflow the agent follows (inspect → recommend → prepare → synth → train → eval → serve)
- [ ] `skill/vakforge/references/`: decision guide, data format, locale rules, data ethics, recipe pitfalls, upstream-verification rules
- [ ] Skill calls the core CLI for schema, validation, recommend; generates recipe glue per project
- [ ] Tested on one real project end to end (documents + tables, no audio) and one with call recordings

## Phase 3 — Landing page
- [ ] `site/` static page on GitHub Pages: what it is, bring-any-data table, pipeline, locale packs, install, skill install
- [ ] Brand assets committed under `assets/`

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
- [ ] Realtime-compatible WebSocket (documented event subset), Python client, Pipecat and LiveKit examples, Dockerfile

## Phase 6 — More recipes (contributor-friendly)
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
