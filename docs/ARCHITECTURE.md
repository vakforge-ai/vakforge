# Architecture

## Principles

1. **One canonical format in the middle.** Raw data → canonical manifest → recipe adapters. Nothing crosses that line sideways.
1b. **Locale packs own everything language- or market-specific.** Core asks the pack; it never branches on a language string.
2. **Core has no ML dependencies.** `schema`, `validate`, `inspect`, `recommend`, `report` import only the standard library, pydantic, numpy, soundfile, rich, typer.
3. **Recipes are plugins.** Each lives in its own package with its own optional extra, lazy imports, and its own integration tests. Adding a recipe never touches core.
4. **Wrap upstream, don't fork.** `moshi-finetune`, `liquid-audio`, Unsloth, NeMo are pinned dependencies called through thin adapters. If an upstream needs a patch, keep it as a `patches/*.patch` applied at install time, and open an upstream PR.
5. **Everything is reproducible from a manifest hash + config file + pinned versions.**

## Package layout

```
vakforge/
  __init__.py
  cli.py                    # typer app; one subcommand per stage; thin, delegates
  config.py                 # pydantic settings; YAML load; CLI override merge
  schema.py                 # canonical models (Conversation, Turn, ToolCall, Meta …)
  validate.py               # rules from DATA_FORMAT.md; returns structured errors

  locales/
    base.py                 # LocalePack protocol + registry (see LOCALE_PACKS.md)
    en.py                   # parent + en-US/en-GB/en-IN skeletons; split into packages as they grow
    hi_latn_in/             # Roman-Hindi detection, transliteration, Indian generators
    zh_cn/                  # planned

  inspect/
    sources.py              # walk a data dir; classify documents, tables, chats (JSONL, WhatsApp), audio
    profile.py              # shallow facts per kind: words/languages/PII, columns/id columns, messages, audio stats
    report.py               # folder summary + inspect.json; one bad file never aborts the run

  recommend/
    questionnaire.py        # interactive prompts (typer)
    rules.py                # DECISION_GUIDE.md as data + a small rules engine

  prepare/
    normalize.py            # resample to 24 kHz, channel handling, loudness
    transcribe/             # engine interface + faster_whisper.py, indic_conformer.py, paraformer.py
    diarize/                # engine interface + channels.py, pyannote.py
    langtag.py              # calls locale.detect_lang per turn
    normalize_text.py       # calls locale.normalize_text; shared punctuation/case rules
    redact/                 # shared patterns + locale.pii_patterns + NER; writes redaction logs
    split.py                # leak-free splits
    build_manifest.py       # assemble canonical rows

  synth/
    scenarios/              # base YAML scenario templates; locale variants live in the pack
    dialogue_llm.py         # provider-agnostic LLM client (OpenAI-compatible or local)
    tts/                    # engine interface + generic_en.py, indic_parler.py, indicf5.py, cosyvoice.py
    mix.py                  # stereo assembly, overlaps, backchannels
    augment.py              # phone band-pass, noise, reverb, codec artefacts
    build.py                # produce canonical manifest with meta.source="synthetic"

  adapters/
    base.py                 # Adapter protocol: manifest → recipe dataset dir + manifest_hash
    lfm25_audio.py
    moshi.py
    qwen_omni.py
    cascade.py

  recipes/
    base.py                 # Recipe protocol: prepare(), train(), load_for_eval(), serve()
    lfm25_audio/            # extra: lfm25
    moshi_lora/             # extra: moshi
    qwen_omni/              # extra: qwen
    cascade/                # extra: cascade

  eval/
    metrics/                # wer.py, entities.py, tool_calls.py, latency.py, duplex.py, voice.py, judge.py
    runner.py               # runs base + tuned on held-out split via recipe.load_for_eval()
    report.py               # report.md + report.json

  serve/
    protocols/              # wire-format front ends over one StreamingBackend
      realtime_ws.py        # OpenAI Realtime WebSocket format (documented subset), first
      webrtc.py             # LiveKit / Pipecat transports, next
      sip.py                # telephony, next
      http.py               # one turn per request, planned
    session.py              # per-connection state, audio buffers, tool dispatch
    adapters/               # recipe → streaming inference interface
    examples/               # python_client.py, pipecat_pipeline.py, livekit_agent.py

  utils/
    audio.py, hashing.py, logging.py, hf.py (gated-model helpers)

skill/vakforge/             # agent skill: SKILL.md + references/ distilled from docs/
site/                       # static landing page (GitHub Pages)
site/assets/                # brand and site images (served by Cloudflare Pages)
configs/                    # default YAML per recipe
notebooks/                  # Colab notebooks, one per recipe
tests/
  unit/                     # CPU, no downloads, always run
  integration/              # @pytest.mark.model / @pytest.mark.gpu, opt-in
  fixtures/                 # generated in conftest.py, not committed binaries
docs/
benchmarks/vakforge-bench-<locale>-v0/
```

## Key interfaces

```python
class Adapter(Protocol):
    name: str

    def build(self, manifest: Path, out_dir: Path, cfg: AdapterConfig) -> AdapterOutput: ...

    # AdapterOutput: out_dir, manifest_hash, stats (rows kept/dropped and why)


class Recipe(Protocol):
    name: str
    extra: str  # uv extra that provides deps

    def check_env(self) -> list[EnvIssue]: ...  # missing deps, GPU, gated weights
    def train(self, dataset: AdapterOutput, cfg: TrainConfig) -> TrainResult: ...
    def load_for_eval(self, checkpoint: Path | None) -> Inferencer: ...  # None = base model
    def serve(self, checkpoint: Path | None, cfg: ServeConfig) -> StreamingBackend: ...


class Inferencer(Protocol):
    def respond(self, session: EvalSession) -> EvalTurnResult: ...

    # returns text, audio (24 kHz), tool_calls, timings (ttft, ttfa, total)


class StreamingBackend(Protocol):
    async def append_audio(self, pcm16: bytes) -> None: ...
    async def commit(self) -> None: ...
    async def responses(self) -> AsyncIterator[RealtimeEvent]: ...
    async def tool_result(self, call_id: str, content: dict) -> None: ...
```

`eval` and `serve` depend only on these protocols, so a new recipe that implements them gets the full report and every protocol front end for free.

## Data flow

```
docs / tables / chats / audio ─► inspect ─► inspect.json
                │
                ▼
          recommend ─► recipe + data gaps
                │
                ▼
any source ─► prepare ─► data/vakforge.jsonl ◄─ synth
                                │
                                ▼
                    adapters/<recipe>.build()
                                │
                                ▼
                    recipes/<recipe>.train() ─► runs/<ts>/checkpoint + train.json
                                │
                                ▼
                    eval.runner (base vs tuned) ─► runs/<ts>/report.{md,json}
                                │
                                ▼
                    serve.realtime_ws ─► ws://…/v1/realtime
```

## Serving: protocol front ends

The model backend (`StreamingBackend`) knows nothing about the wire. Each protocol is a thin front end in `serve/protocols/` that translates its messages into `append_audio` / `commit` / `responses` / `tool_result`. Every model served is open and local; "OpenAI Realtime compatible" names a message format, not a dependency.

| Front end | Why | Status |
|---|---|---|
| OpenAI Realtime WebSocket | de facto shape for voice agents; GPT Realtime users change one URL; Pipecat, LiveKit, Twilio clients work unchanged | first |
| WebRTC (LiveKit / Pipecat transports) | browsers and mobile, lowest latency, echo cancellation for free | next |
| SIP | telephony, the call-centre use case | next |
| HTTP | one turn per request for batch and simple integrations | planned |
| Gemini Live format | teams on Google's stack | on request |

A new front end ships with its own event list in `serve/README.md` and a contract test against a fake backend.

### OpenAI Realtime WebSocket subset

We implement a documented subset, enough for common clients:

- Client → server: `session.update`, `input_audio_buffer.append`, `input_audio_buffer.commit`, `input_audio_buffer.clear`, `response.create`, `response.cancel`, `conversation.item.create` (for `function_call_output`).
- Server → client: `session.created`, `input_audio_buffer.speech_started/stopped` (VAD), `response.created`, `response.audio.delta`, `response.audio_transcript.delta`, `response.function_call_arguments.done`, `response.done`, `error`.
- Audio: PCM16 24 kHz base64, matching the common default.

Unsupported events return a structured `error` naming the event. The exact list lives in `serve/README.md` and is tested.

## Run directory

```
runs/2026-09-16T10-12-00_lfm25-audio/
  config.yaml            # fully resolved
  manifest_hash.txt
  versions.txt           # pip freeze of the recipe env
  train.log
  checkpoint/            # adapter or full weights
  report.md / report.json
```
