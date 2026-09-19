# Decision rules

`vakforge recommend` applies these; read this when you need to explain or challenge its output.
Full text: `docs/DECISION_GUIDE.md` in the vakforge repo.

## Goals and their fix

| Goal (`--goal`) | The user wants the assistant to | Fix | Not this |
|---|---|---|---|
| `knowledge` | know products, prices, policies, FAQs | retrieval at answer time; facts stay out of weights | fine-tuning (facts go stale, hallucinate) |
| `tools` | book, check status, open tickets reliably | tool definitions over the tables; tool-use fine-tune only if the base model keeps missing | hoping prompts hold under noisy audio |
| `workflow` | follow the call flow: greet, verify, act, confirm | behaviour fine-tune of the language side | prompt-only if it fails more than 20% of scripted flows |
| `recognition` | understand local names, addresses, amounts, accents, code-switching | speech-to-text or audio-encoder fine-tune | fine-tuning only the text side |
| `voice` | speak in a specific voice | voice cloning or TTS speaker fine-tune, with written consent | retraining a conversation model |
| `duplex` | handle interruptions, stop when the user talks, sound natural | full-duplex model trained on real stereo calls | turn-based model with VAD hacks |
| `language` | speak a non-English language natively | locale pack plus a model the pack marks `native`, else the cascade | fine-tuning an English-only model to a new language on a small dataset |

Most real requests are two or three goals. Each has its own data need and metric.

## What the data allows

| Data | Usable for |
|---|---|
| documents only | retrieval; synthetic dialogues; then any recipe |
| tables, CRM | tools; synthetic dialogues that exercise every tool |
| chat logs, transcripts | behaviour fine-tune of the language side; render to audio with synth |
| mono call recordings | diarize first; speech-to-text and turn-based recipes; weak for duplex |
| stereo recordings (agent and customer on separate channels) | everything, including duplex |
| clean studio recordings of one voice | voice cloning |

Quantity: a few hundred to a few thousand *turns* covering every branch of the flow for
behaviour; tens of hours of real conversation for voice, style or duplex. The CLI uses 600
turns as the behaviour target, refuses to recommend training under 200, and wants 10+ hours
for voice or duplex.

## Constraints

- Latency: sub-300 ms with interruptions → duplex recipe. 500 to 900 ms turn-based → `lfm25-audio` or cascade.
- Hardware: 24 GB → `lfm25-audio`, cascade. 48 GB+ → `moshi-lora`. 80 GB or multi-GPU → `qwen-omni`.
- Deployment on CPU, edge or browser → `lfm25-audio` (GGUF, ONNX).
- Locale: the pack's `recipe_support` decides; `understand_only` means input is understood but speech output stays English.

## Do not fine-tune when

- the failure is factual (wrong price, wrong policy): retrieval
- the base model has not been measured on the held-out set yet: measure first
- there is no consent trail for the data: fix that first
- fewer than a couple of hundred conversation turns exist: synthesise and collect

Fine-tune when, after prompt plus retrieval, the base model still fails a scripted-flow or
tool-call test set at a rate the user cannot ship, or recognition errors are dominated by
things a prompt cannot fix.
