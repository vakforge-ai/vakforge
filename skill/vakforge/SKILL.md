---
name: vakforge
description: >
  Build a self-hosted voice assistant from a company's own data (documents, database tables,
  chat logs, CRM exports, call recordings) using open voice models. Use when asked to build,
  fine-tune, evaluate or self-host a voice agent or voice bot; to decide between fine-tuning
  and retrieval (RAG) for voice; to replace a hosted voice API such as OpenAI Realtime with an
  open model; to handle Hinglish, Indian English or another locale in a voice agent; or when
  the user mentions vakforge.
---

You are turning a company's data into a voice assistant that runs on their hardware, with the
`vakforge` CLI making the decisions and you writing the per-project glue. The knowledge is in
this skill and its references; the pipeline code does not exist until you generate it.

Two gates rule the whole job. **Nothing is trained before `recommend` says so. Nothing ships
before `eval` shows the tuned model beats the base model on held-out data.**

## Hard rules

- **Verify before you call.** Before using any upstream library (`liquid_audio`, `moshi`,
  `moshi-finetune`, `ms-swift`, `transformers`, `peft`, `pyannote`, `faster_whisper`, Pipecat,
  LiveKit), open its installed source (`python -c "import x; print(x.__file__)"`, then read
  the signatures you need) or the pinned GitHub commit. Signatures you could not read get a
  `# TODO(verify)` comment, a skipped test, and a sentence to the user. Never guess an API.
- **Locale packs, not if-statements.** Currency, dates, phone and ID formats, scripts, names,
  consent rules and preferred models come from `vakforge locales <id>`
  (`references/locales.md` lists the Python hooks). Core-style code you write never
  branches on a language string.
- **Redaction and consent are steps, not options.** Every training row carries a consent
  basis and a redaction status. A flag that weakens either logs a loud warning. Never put real
  customer data, names, IDs or audio in tests, issues, prompts you send elsewhere, or files you
  publish.
- **Open models on the user's hardware.** Nothing calls OpenAI or another hosted API for the
  assistant itself. "Realtime compatible" means the wire format only.
- **Ask before spending.** Any model download over 500 MB, any GPU job over a few minutes,
  any paid API call for synthetic data: ask first, with the size and the cost.
- **CPU-testable.** Everything you write has a test that passes on CPU with no downloads.
  GPU and model-download tests are marked `@pytest.mark.gpu` / `@pytest.mark.model`.

## Workflow

Run the steps in order. Each step names what "done" means; do not start the next before it.

### 1. Set up

```bash
pip install vakforge            # or: uv add vakforge
vakforge locales                # pick the locale pack(s) for the user's market
vakforge init <project> --locale <id> [--locale <id2>]
```

Done when the project folder exists and the user has put their data under
`<project>/data/raw/` (or told you where it is).

### 2. Inspect

```bash
vakforge inspect <project>/data/raw
```

Read `inspect.json` in full. Done when you can state, in one paragraph to the user: which
source kinds exist, how many conversation turns and audio hours, which languages appear,
what personal data was found, which files were skipped and why, and which tool candidates
the tables suggest.

### 3. Recommend

```bash
vakforge recommend inspect.json [--goal ...] [--gpu 24|48|80] [--duplex]
```

Ask the user for the three constraints if you do not know them: what should improve (see
`references/decision-rules.md` for the goal list), the largest GPU they can train on, and
whether callers must be able to interrupt. Read `recommend.json`. Done when the user has
approved a plan that states: the routes per source, whether a fine-tune is on the table at
all, the recipe and its locale support level, the data gap, the consent checklist, and the
hardware and cost. If `fine_tune` is false, the plan is retrieval plus tools plus synthetic
dialogues, and you skip step 6.

### 4. Prepare

Write `<project>/prepare/` so that it turns the raw sources into `data/vakforge.jsonl` in
the canonical format (`references/data-format.md`), following `references/data-safety.md`:
consent prompt once per source folder, redaction of text and audio with a log and a
keep-list, per-turn language tags from the locale pack, splits by conversation and speaker.

Done when `vakforge validate <project>/data/vakforge.jsonl` reports zero issues and your
CPU tests pass on a synthetic fixture.

### 5. Synthesise (when the data gap says so)

Write `<project>/synth/`: scenario templates in the user's locale, a provider-agnostic
dialogue generator (any OpenAI-compatible endpoint or a local model, the user chooses and
you ask before paid calls), explicit tool calls plus a no-tool chitchat class, rendered with
an open TTS from `vakforge locales <id>` when audio is needed. Rows carry
`meta.source = "synthetic"` and `meta.consent = "synthetic"`.

Done when the manifest validates and the turn count meets the gap `recommend` reported.

### 6. Baseline, then train only what was recommended

Always measure first: the base model with the system prompt, retrieval over the documents
and the tool definitions, on the held-out split, using the metrics in
`references/eval.md`. Show the user the numbers. Then, only if `recommend` said yes and the
baseline still fails, write `<project>/train/` for the chosen recipe from
`references/recipes.md`, pinning every upstream version.

Done when a run directory holds the resolved config, the manifest hash, `versions.txt`, the
checkpoint, and a training log.

### 7. Evaluate

Write `<project>/eval/` that emits `report.md` and `report.json` in the shape given in
`references/eval.md`, broken down by locale, language, audio condition and source. Two
branches:

- **No fine-tune** (step 6 was skipped): score the retrieval + tools stack on the held-out
  split against the acceptance targets the user agreed to in step 3.
- **Fine-tune**: score base and tuned on the same held-out split; the tuned model must beat
  the base on the metrics `recommend` named, with regressions inside the agreed budget.

Done when the report exists and you have told the user, in plain words, what got better,
what got worse, and whether it should ship.

### 8. Serve

Only after eval says ship. Write `<project>/serve/` following `references/eval.md`
(protocol section): the model backend behind an OpenAI Realtime WebSocket front end with the
documented event subset, a 50-line Python client, and a Dockerfile. Done when the client
completes one round trip against the running server and latency is measured through it.

## Reporting to the user

At the end of every step: what works, what is stubbed with `TODO(verify)`, what you verified
against upstream source and where, and what it will cost to continue. Numbers in a table;
one recommendation, not a menu.
