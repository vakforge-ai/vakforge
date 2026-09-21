<p align="center">
  <img src="https://vakforge.pages.dev/assets/social/readme-banner.png" alt="vakforge: your data, your voice assistant, your hardware" width="100%">
</p>

# vakforge

**The decision layer for open voice AI.**

vakforge helps you build a voice assistant from the data your company already has, and run it on your own servers. Before you spend anything on GPUs, it tells you what actually needs training. Usually that is less than you think.

<p align="center">
  <img src="https://vakforge.pages.dev/assets/diagrams/decision-layer-light.webp" alt="Documents, database tables, chat logs and call recordings go into vakforge, which inspects them and recommends retrieval, tools, fine-tuning or a locale pack. The result is your voice assistant, on your servers." width="100%">
</p>

- **Bring any data:** documents, FAQs, database tables, chat logs, CRM records, recorded calls.
- **Open models only:** the assistant itself runs on your servers and never calls a hosted API. (Generating synthetic training dialogues may use a provider you choose, only after you approve it.)
- **Any language:** through locale packs. Launching with English (US, UK, India) and Hinglish.

> Status: pre-alpha. `init`, `validate`, `inspect` and the locale packs work today. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Why vakforge exists

Open voice models are good enough today. Moshi, PersonaPlex, LFM2.5-Audio and Qwen-Omni can listen and talk, and strong open speech-to-text and text-to-speech models exist too. Yet most companies still pay per minute for a closed voice API.

That is not because the open models are worse. It is because nobody helps them answer four questions:

- Should we fine-tune, or is retrieval enough?
- Which model fits our language, our speed needs and our hardware?
- What data do we need, and are we allowed to train on our calls?
- How do we prove the result is better before a customer hears it?

vakforge answers them from your own data.

The hard part was never the models. It was the decision.

> "Open models strengthen safety and cybersecurity, accelerate innovation and diffusion, and enable sovereignty."
> Jensen Huang, NVIDIA, [on X, 24 July 2026](https://finance.yahoo.com/technology/ai/articles/jensen-huang-just-used-first-175154980.html)

vakforge is about that last word: owning your voice AI instead of renting it.

## How it works

<p align="center">
  <img src="https://vakforge.pages.dev/assets/diagrams/workflow-light.webp" alt="Seven steps: init, inspect, recommend, prepare, train, eval, serve. Recommend and eval are decision gates." width="100%">
</p>

1. **`init`** creates a project folder for your language and market.
2. **`inspect`** reads your data folder and reports what is in it: languages, personal data, tables that could become tools, audio quality.
3. **`recommend`** decides what needs changing. Often the answer is retrieval and tools, with no training at all.
4. **`prepare`, `train`, `eval`, `serve`** are built for your project by a coding agent using the vakforge skill. It trains only what `recommend` asked for, and ships only if `eval` shows the result beats the base model.

Today the CLI covers `init`, `inspect`, `recommend`, `validate` and the locale packs.

## How the decision is made

| If the assistant should... | The fix is | Training? |
|---|---|---|
| know your prices, policies and FAQs | retrieval: look facts up at answer time | none |
| look things up, book, open tickets | tools over your tables | only if it keeps missing |
| follow your call flow and tone | behaviour fine-tune of the language model | small |
| understand your callers' accents, names, amounts | speech-to-text fine-tune | small |
| sound like your brand | voice cloning, with written consent | voice only |
| handle interruptions naturally | a full-duplex model trained on real calls | large |
| speak another language | a locale pack plus a model that speaks it | depends |

Every route ends the same way: test it against your own held-out data, and ship only if it beats the base model.

Each goal has its own fix, and most of them are not a full fine-tune. The detailed rules, with how much data each route needs and what hardware it takes, are in [`docs/DECISION_GUIDE.md`](docs/DECISION_GUIDE.md).

## The problem, for engineers

Open speech-to-speech models exist. Fine-tuning scripts exist for some of them. Evaluation tools and serving frameworks exist. What is missing is one path from *"here is what my company knows"* to *"here is a voice assistant that handles my workflow, I can prove it is better than the base model, and my existing voice client can talk to it without a rewrite."* Every team rebuilds that path, and most of them fine-tune when they should have used retrieval.

## What's in the repo

1. **A small library and command-line tool** (`pip install vakforge`). No machine-learning dependencies, so it runs on any laptop. It holds the dataset format, the data checks, the data inspector, the decision rules and the locale packs.
2. **An agent skill** (`skill/vakforge/`). Add it to Claude Code or another coding agent. The agent reads your data, follows the decision rules, and writes the training and serving code for your project. It checks every library it uses against the installed source first, so it does not guess at APIs.
3. **Recipes** ([`docs/RECIPES.md`](docs/RECIPES.md)). Written-down, tested paths from an open base model to a running assistant. Only recipes someone has run end to end get listed.

| Command | What it does | Status |
|---|---|---|
| `vakforge init` | Create a project folder for your language and market | works |
| `vakforge inspect` | Report what is in your data folder | works |
| `vakforge validate` | Check a dataset file against the vakforge format | works |
| `vakforge locales` | List language packs and show their rules | works |
| `vakforge schema` | Export the dataset format as JSON Schema | works |
| `vakforge recommend` | Decide what needs changing, often "retrieval, not training" | works |
| `prepare`, `synth`, `train`, `eval`, `serve` | Build, test and host the assistant | written per project by the agent skill |

## Use it with a coding agent

The skill is where the knowledge lives. Copy it into your project and the agent follows the
vakforge workflow: inspect, recommend, then write and test the prepare, train, eval and serve
code for your case, verifying every upstream API against installed source first.

```bash
# Claude Code: project-level skill (or ~/.claude/skills/vakforge for every project)
mkdir -p .claude/skills
cp -r path/to/vakforge/skill/vakforge .claude/skills/vakforge
```

Then ask: *"Build a Hinglish support assistant from the data in data/raw."* Other agents that
read `SKILL.md`-style instructions work the same way; point them at the folder.

## Bring any data

| You have | What vakforge does with it |
|---|---|
| Documents, FAQs, policies | Looks facts up at answer time (retrieval), so prices and policies stay current without retraining. |
| Database tables, CRM, product catalogue | Turns them into tools the assistant can call, like "look up order by order id". |
| Chat logs, transcripts | Teaches the assistant how your team handles a conversation: steps, tone, hand-offs. |
| Recorded calls | Everything above, plus your callers' accents and the natural timing of real calls. Personal data is removed first. |
| Nothing yet | Generates example conversations in your language, so you can ship a first version and collect real data. |

## Locale packs

The core works in any language. Everything that changes by language or country lives in a locale pack: how money, dates and phone numbers are written, which ID numbers count as personal data, the local privacy and call-recording rules, and which open models support the language. Adding a new market means adding a pack, not changing the core. See [`docs/LOCALE_PACKS.md`](docs/LOCALE_PACKS.md), or run `vakforge locales`.

| Pack | Covers | Can the assistant speak it? | Status |
|---|---|---|---|
| `en-US`, `en-GB`, `en-IN` | US, UK and Indian English | yes, with every recipe | works |
| `hi-Latn-IN` | Hinglish: Hindi and English mixed, in Roman or Devanagari script | understands it; speaks English, or Hindi through the cascade recipe | works |
| `zh-CN` | Mandarin | via `qwen-omni` | planned |
| `es`, `de`, `fr`, `pt-BR`, `ja`, `ar` | | via `qwen-omni` or cascade | planned, contributions welcome |

## Recipes

| Recipe | Base model | Good for | Duplex | Hardware (train) | Status |
|---|---|---|---|---|---|
| `lfm25-audio` | LiquidAI LFM2.5-Audio-1.5B | workflow, tool use, style, CPU deploy | turn-based | 1x 24 GB GPU | planned (first) |
| `moshi-lora` | Kyutai Moshi / NVIDIA PersonaPlex | interruptions, natural timing, persona | full-duplex | 1x 40-80 GB GPU | planned |
| `qwen-omni` | Qwen3-Omni | multilingual incl. Mandarin, function calling | near-duplex | 80 GB / multi-GPU | planned |
| `cascade` | STT + LLM LoRA + TTS chosen by locale | any language with a good STT+TTS pair | turn-based | 1x 24 GB GPU | planned |

"Duplex" means the assistant can listen while it talks, so callers can interrupt it naturally. Details in [`docs/RECIPES.md`](docs/RECIPES.md).

## Connecting your app

Your assistant runs an open model on your own servers. Nothing calls OpenAI or any other hosted API.

To make switching easy, the server accepts the same WebSocket messages as OpenAI's Realtime API. If your app already talks to GPT Realtime, you change one URL. Tools like Pipecat, LiveKit and Twilio keep working as they are. More connection types can be added without touching the model:

| Protocol | For | Status |
|---|---|---|
| OpenAI Realtime WebSocket (documented subset) | teams migrating off GPT Realtime; Pipecat, LiveKit, Twilio clients | first |
| WebRTC via LiveKit or Pipecat transports | browser and mobile apps, lowest latency | next |
| SIP / telephony | call centres and phone lines | next |
| Plain HTTP, one turn per request | batch jobs, simple integrations | planned |
| Gemini Live API format | teams on Google's stack | on request |

## Why English and Hinglish first

English has the strongest open voice models, so every recipe works for US, UK and Indian English. Hinglish is the hard test: people switch between Hindi and English mid-sentence, write Hindi in Roman or Devanagari script, and say amounts like "2 lakh rupees" on noisy phone lines. If vakforge handles that, adding another language is mostly filling in a new pack.

## Quick start

```bash
pip install vakforge
vakforge init my-assistant --locale hi-Latn-IN
# put your documents, tables, chat exports and call recordings in my-assistant/data/raw/
vakforge inspect my-assistant/data/raw
```

`inspect` prints a summary and writes `inspect.json`. `vakforge recommend inspect.json` reads it and writes `recommend.json`.

## Documentation

- [`docs/DECISION_GUIDE.md`](docs/DECISION_GUIDE.md): what needs customizing, and when not to fine-tune
- [`docs/LOCALE_PACKS.md`](docs/LOCALE_PACKS.md): what a locale pack contains, and how to add one
- [`docs/DATA_FORMAT.md`](docs/DATA_FORMAT.md): the dataset format
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): how the code fits together, with diagrams
- [`docs/RECIPES.md`](docs/RECIPES.md): per-model training recipes
- [`docs/EVALUATION.md`](docs/EVALUATION.md): metrics, report format, per-locale benchmarks
- [`docs/DATA_ETHICS.md`](docs/DATA_ETHICS.md): consent, PII, licences, privacy law by region
- [`docs/ROADMAP.md`](docs/ROADMAP.md): status
- [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Related projects (we build on these, not against them)

Unsloth, LLaMA-Factory, ms-swift, kyutai-labs/moshi-finetune, NVIDIA PersonaPlex, liquid-audio, Qwen-Omni, Pipecat, LiveKit Agents, vLLM-omni, UltraEval-Audio, AI4Bharat, Common Voice

## Licence

Apache-2.0 for this code. Each open model keeps its own licence; see [`docs/RECIPES.md`](docs/RECIPES.md). Datasets you create with vakforge are yours. The consent records vakforge asks for are there to keep it that way.
