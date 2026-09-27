# AGENTS.md: vakforge

The working rules for this repo, for contributors and for any coding agent they use. Keep it short and current.

## What this repo is

`vakforge` turns the data a company already has (documents, database tables, chat logs, CRM records, recorded calls) into a self-hosted, evaluated, real-time voice assistant served from open models on the user's hardware, behind standard protocols (OpenAI Realtime WebSocket format first; WebRTC and SIP next). "Realtime compatible" means the wire format only; nothing calls a hosted API. Any language via locale packs; launch locales English (en-US/en-GB/en-IN) and Hinglish (hi-Latn-IN). Ships as: zero-ML-dep core library + CLI, an agent skill under `skill/`, a landing page under `site/`, and GPU recipes as optional extras. Full spec lives in `docs/`.

## Read first

1. `docs/ROADMAP.md`: current phase and what is done/stubbed.
2. `docs/ARCHITECTURE.md`: package layout and boundaries.
3. `docs/DATA_FORMAT.md`: canonical schema; all recipes go through it.
4. `docs/LOCALE_PACKS.md`: anything language/market-specific lives in a pack, never in core.
5. The recipe you are touching in `docs/RECIPES.md`.

## Hard rules

- Verify every upstream API against installed source (`python -c "import x; print(x.__file__)"` then read it) or the pinned GitHub commit. Never guess signatures. Unverifiable → `# TODO(verify)` + skipped test, and say so in the pull request.
- `pytest` passes on CPU with no downloads. GPU/model tests are marked `@pytest.mark.gpu` / `@pytest.mark.model` and excluded by default.
- Ask before: downloading models > 500 MB, GPU jobs > a few minutes, any paid API call.
- Recipes are optional extras with lazy imports. Core (`schema`, `inspect`, `validate`, `recommend`, `locales`) must import with zero ML deps.
- No `if lang == "..."` in core. Currency, dates, phone/ID formats, scripts, names, privacy notes, preferred models → the locale pack.
- PII redaction and consent metadata are mandatory steps in `prepare`; never add a flag that silently skips them without logging a warning.
- Update `docs/ROADMAP.md` checkboxes in the same commit as the feature.

## Commands

```bash
uv sync --group dev           # core + pytest/ruff
uv sync --extra lfm25         # recipe A deps
uv sync --extra moshi         # recipe B deps
uv sync --extra qwen          # recipe D deps
uv sync --extra cascade       # recipe C deps
uv run pytest                 # CPU tests, no downloads
uv run pytest -m gpu          # GPU tests (opt-in)
uv run ruff check . && uv run ruff format .
uv run vakforge --help
```

## Conventions

- Python 3.11+, `typer` CLI, `pydantic` v2, `rich` output, `soundfile`/`torchaudio` for audio, `jiwer` for WER.
- Audio internal standard: 24 kHz, float32, mono per stream; stereo files = channel 0 user, channel 1 agent.
- Language tags: BCP-47 (`en-US`, `en-GB`, `en-IN`, `hi`, `hi-Latn` for Roman Hindi, `zh-CN`). Locale pack ids add region (`hi-Latn-IN`). Code-switched turns carry `lang` = primary + `lang_mix` list.
- Config files are YAML validated by pydantic; CLI flags override config.
- Conventional commits. One logical change per commit.
- Docstrings on public functions; type hints everywhere; no bare `except`.

## Things that have bitten us (append as you learn)

- Model libraries pin conflicting `torch`/`transformers` versions → that is why recipes are isolated extras.
- pyannote diarization weights are gated on Hugging Face; document the acceptance step, never bundle weights.
- Whisper family mislabels Roman Hindi as English or Hindi inconsistently → run the locale pack's `detect_lang` after transcription. Expect the same for any code-switched locale.
- Thinker-only Qwen-Omni checkpoints from some frameworks can't be loaded by the full model without re-keying → adapter must merge Talker/code2wav from the vanilla checkpoint and test the round trip.
