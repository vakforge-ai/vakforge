# vakforge

**Turn the data your company already has into a self-hosted, real-time voice assistant.**

Documents, FAQs, database tables, chat logs, CRM records, recorded calls: vakforge works out what your assistant actually needs (knowledge, behaviour, tools, voice, language), generates the conversational data you lack, trains only what needs training, proves the result beats the base model on your own held-out data, and serves it behind an OpenAI-Realtime-compatible WebSocket. Open source, runs on your hardware, any language through locale packs. Launch locales: English (US, UK, India) and Hinglish.

> Status: pre-alpha. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what exists today.

## The problem

Open speech-to-speech models exist (Moshi, PersonaPlex, LFM2.5-Audio, Qwen-Omni). Fine-tuning scripts exist for some of them. Evaluation tools exist. Serving frameworks exist. What does not exist is one path from *"here is what my company knows"* to *"here is a voice assistant that handles my workflow, I can prove it is better than the base model, and it answers a WebSocket like GPT Realtime does."* Every team rebuilds that path badly, and most of them fine-tune when they should have used retrieval.

## What ships

vakforge is three things in one repo:

1. **A core library and CLI** (`pip install vakforge`). Zero ML dependencies. Canonical dataset schema, validator, data inspector, decision engine, locale packs. Runs on a laptop.
2. **An agent skill** (`skill/`). Drop it into Claude Code or any coding agent. The agent reads your data, runs the decision guide, writes the recipe-specific glue for your project, and verifies every upstream API against source before using it. The knowledge lives here; the glue code is generated per project.
3. **Recipes** (`docs/RECIPES.md`). Tested paths from base model to served assistant. Each is an optional extra, isolated because model libraries conflict. Only recipes run end to end get listed.

```
vakforge inspect ./data        ->  what is actually in your documents, tables, chats, audio
vakforge recommend             ->  what needs customizing (often: retrieval, not the model)
vakforge prepare               ->  ingest, transcribe, redact PII, canonical dataset
vakforge synth                 ->  synthetic dialogues in your locale over your tools and facts
vakforge train --recipe X      ->  one tested recipe, not a menu of 400 models
vakforge eval                  ->  base vs tuned: WER, entities, tool calls, latency, voice
vakforge serve                 ->  OpenAI-Realtime-compatible WebSocket; re-point your client
```

## Bring any data

| You have | vakforge does |
|---|---|
| Documents, FAQs, SOPs, knowledge base | Retrieval at inference. Facts stay out of weights. Synthetic dialogues grounded in them. |
| Database tables, CRM, product catalogue | Tool definitions over your data, synthetic dialogues that exercise every tool, behaviour fine-tune for reliable tool use. |
| Chat logs, transcripts | Behaviour and workflow fine-tune of the language component; rendered to audio via `synth`. |
| Recorded calls (mono or stereo) | Transcribe, diarize, redact, then everything above plus voice, timing and full-duplex recipes. |
| Nothing yet | Scenario templates in your locale, rendered with open TTS, so you can ship a v0 and collect real data. |

## Locale packs

The pipeline is language-agnostic. Everything language- or market-specific lives in a locale pack: number/currency/date/address formats, PII patterns, privacy-law notes, name generators for synthetic data, preferred models, and a benchmark. See [`docs/LOCALE_PACKS.md`](docs/LOCALE_PACKS.md).

| Pack | Covers | Speech output today | Status |
|---|---|---|---|
| `en` | en-US, en-GB, en-IN | native (all recipes) | launch |
| `hi-Latn` | Hinglish / Roman Hindi, Hindi-English code-switching | English output; Hindi via cascade | launch, the hard-case showcase |
| `zh-CN` | Mandarin | via `qwen-omni` | planned |
| `es`, `de`, `fr`, `pt-BR`, `ja`, `ar` | | via `qwen-omni` or cascade | planned, contributions welcome |

## Recipes

| Recipe | Base model | Good for | Duplex | Hardware (train) | Status |
|---|---|---|---|---|---|
| `lfm25-audio` | LiquidAI LFM2.5-Audio-1.5B | workflow, tool use, style, CPU deploy | turn-based | 1x 24 GB GPU | planned (first) |
| `moshi-lora` | Kyutai Moshi / NVIDIA PersonaPlex | interruptions, natural timing, persona | full-duplex | 1x 40-80 GB GPU | planned |
| `qwen-omni` | Qwen3-Omni | multilingual incl. Mandarin, function calling | near-duplex | 80 GB / multi-GPU | planned |
| `cascade` | STT + LLM LoRA + TTS chosen by locale | any language with a good STT+TTS pair | turn-based | 1x 24 GB GPU | planned |

Details in [`docs/RECIPES.md`](docs/RECIPES.md).

## Why launch with English and Hinglish

English is where the strongest open speech-to-speech models are, so every recipe works out of the box for US, UK and Indian English. Hinglish is the stress test: code-switching, Roman vs Devanagari script, Indian names and rupee amounts, noisy phone lines. If the pipeline handles that, a new locale pack is mostly formats and models, not new architecture.

## Quick start (target UX, not all steps implemented yet)

```bash
uv sync
uv run vakforge init my-assistant --locale en-US && cd my-assistant
uv run vakforge inspect ./data
uv run vakforge recommend
```

## Documentation

- [`docs/DECISION_GUIDE.md`](docs/DECISION_GUIDE.md): what actually needs customizing; when not to fine-tune
- [`docs/LOCALE_PACKS.md`](docs/LOCALE_PACKS.md): what a locale pack contains; how to add one
- [`docs/DATA_FORMAT.md`](docs/DATA_FORMAT.md): canonical dataset schema
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): package layout
- [`docs/RECIPES.md`](docs/RECIPES.md): per-model training recipes
- [`docs/EVALUATION.md`](docs/EVALUATION.md): metrics, report format, per-locale benchmarks
- [`docs/DATA_ETHICS.md`](docs/DATA_ETHICS.md): consent, PII, licences, privacy law by region
- [`docs/ROADMAP.md`](docs/ROADMAP.md): status
- [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Related projects (we build on these, not against them)

Unsloth, LLaMA-Factory, ms-swift, kyutai-labs/moshi-finetune, NVIDIA PersonaPlex, liquid-audio, Qwen-Omni, Pipecat, LiveKit Agents, vLLM-omni, UltraEval-Audio, AI4Bharat, Common Voice

## Licence

Apache-2.0 for this code. Each recipe's base model has its own licence, see `docs/RECIPES.md`. Datasets you create with vakforge are yours; the consent metadata we require is there to keep it that way.
