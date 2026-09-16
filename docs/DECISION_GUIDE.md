# Decision guide — what actually needs customizing?

`vakforge recommend` implements this guide. It exists because "fine-tune on my data" hides six different problems, and fine-tuning is the right answer to only some of them.

## Step 1 — What do you want to change?

| You want the agent to… | The real problem is… | Do this | Not this |
|---|---|---|---|
| Know your products, prices, policies, FAQs | Knowledge | RAG / context injection at inference; keep facts out of weights | Fine-tuning (facts go stale, hallucinate) |
| Follow your call flow (greet → verify → act → confirm) | Behaviour / workflow | Fine-tune the language component (`lfm25-audio` or LLM LoRA) | Prompt-only if it fails >20% of scripted flows |
| Call your tools reliably (book, check status, ticket) | Tool-use behaviour | Fine-tune with tool-call examples + result-narration examples | Hoping prompt engineering holds under noisy audio |
| Understand local names, addresses, amounts, accents, code-switching | Recognition / audio encoder | Fine-tune STT (`cascade`) or the audio encoder in an end-to-end model | Fine-tuning only the text side |
| Speak in a specific voice | Voice identity | Voice cloning / TTS speaker fine-tune | Retraining a conversation model |
| Sound natural: timing, backchannels, emotion | Conversational style | Speech-to-speech fine-tune on real conversations (`moshi-lora`) | Cascaded pipeline (loses paralinguistics) |
| Handle interruptions, stop talking when the user talks | Turn-taking | Full-duplex model + duplex training data (`moshi-lora`) | Turn-based model with VAD hacks |
| Speak a non-English language natively (Hindi, Mandarin, Spanish …) | Language coverage | `qwen-omni` where it covers the language; otherwise `cascade` with the locale pack's STT/TTS | Fine-tuning an English-only S2S model to a new language on a small dataset |

Most real requests are two or three rows at once. That is fine — but each row has its own recipe, data requirement, and evaluation.

## Step 2 — What data do you have?

| Data | Usable for |
|---|---|
| Documents / FAQs / SOPs / knowledge base | Retrieval at inference; synthetic dialogues grounded in them (`synth`) → then any recipe |
| Database tables / CRM / product catalogue | Tool definitions over the data; `synth` dialogues that exercise every tool; behaviour fine-tune for reliable tool use |
| Mono call recordings (both parties mixed) | Needs diarization; usable for STT and turn-based recipes; weak for duplex |
| Stereo recordings (agent/customer separated) | Everything, including `moshi-lora` |
| Clean studio recordings of one voice | Voice cloning; TTS fine-tune |
| Chat logs / transcripts | Behaviour fine-tuning of the language component; render to audio via `synth` |

Rule of thumb for minimum quantity (behaviour/workflow fine-tuning): a few hundred to a few thousand *turns* covering every branch of your flow, not hours. Quality and coverage beat volume. For voice/style/duplex: tens of hours of real conversation.

## Step 3 — Constraints

- **Latency:** need sub-300 ms and interruptions → duplex (`moshi-lora`). Turn-based 500–900 ms acceptable → `lfm25-audio` or cascade.
- **Hardware:** one 24 GB consumer GPU → `lfm25-audio`, `cascade`. 40 GB+ → `moshi-lora`. 80 GB / multi-GPU → `qwen-omni`.
- **Deployment target:** CPU / edge / browser → `lfm25-audio` (GGUF, ONNX). Server GPU → any.
- **Language / locale:** the locale pack declares which recipes are `native`, `understand_only`, `cascade`, or `unsupported` (see `docs/LOCALE_PACKS.md`). Today: English (US/UK/IN) → every recipe; Hinglish → `lfm25-audio`/`moshi-lora` understand Hinglish input but speak English, `cascade` for Hindi output; Mandarin → `qwen-omni` or `cascade`; other languages → `cascade` until native support lands.
- **Market / data residency:** the pack's `privacy_notes` and `call_recording_consent` tell you what `prepare` must collect; some regions (e.g. China, EU) constrain where data and checkpoints may live.
- **Licence:** commercial use → check `docs/RECIPES.md`; PersonaPlex weights are under NVIDIA's open model licence, Moshi under CC-BY-4.0, LFM2.5-Audio under Liquid's licence, Qwen-Omni under Apache-2.0 (confirm per checkpoint) — read them.

## Step 4 — Should you fine-tune at all?

Do **not** fine-tune if:
- The failure is factual (wrong price, wrong policy) → RAG.
- You have not measured the base model on your held-out set yet → run `vakforge eval --baseline-only` first. It is common for a good prompt plus RAG to close most of the gap.
- Your data has no consent trail → fix that first (`docs/DATA_ETHICS.md`).

Fine-tune if, after prompt + RAG, the base model still fails a scripted-flow or tool-call test set at a rate you can't ship, or the accent/entity recognition errors are dominated by things a prompt cannot fix.

## Output of `vakforge recommend`

The command prints: the primary problem class, the recipe (filtered by what the locale pack supports), the minimum data you need (with what you have vs. what's missing), the hardware tier, the eval metrics that will decide success, the locale's consent/privacy checklist, and — when relevant — "you probably don't need to fine-tune; here's the RAG + eval path instead."
