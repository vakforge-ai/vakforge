# Recipes

A recipe is a path from base model → adapter → training → eval → serve.

> **Status: none of these are built.** This file is research, not documentation of working code. Facts were checked in September 2026 against model cards and upstream repositories; **re-verify versions, APIs and licences at implementation time** and update this file. Anything marked *(reported)* comes from third-party write-ups and has not been measured by us.
>
> A recipe only stops being research when it has run end to end on a demo dataset with its `report.json` committed — see the checklist at the bottom.

Locale packs declare per-recipe support (`native | understand_only | cascade | unsupported`); `recommend` reads that, not this file.

## At a glance

| Recipe | Base model | Good for | Duplex | Train on | Status |
|---|---|---|---|---|---|
| [`lfm25-audio`](#recipe-a-lfm25-audio-default-ship-first) | LiquidAI LFM2.5-Audio-1.5B | workflow, tool use, style, CPU deploy | turn-based | 1× 24 GB | research, first to build |
| [`moshi-lora`](#recipe-b-moshi-lora-advanced-full-duplex) | Kyutai Moshi / NVIDIA PersonaPlex | interruptions, natural timing, persona | full-duplex | 40–80 GB | research |
| [`qwen-omni`](#recipe-d-qwen-omni-multilingual-mandarin-first) | Qwen3-Omni | multilingual incl. Mandarin, tool calling | near-duplex | 80 GB or multi-GPU | research |
| [`cascade`](#recipe-c-cascade-any-language) | STT + LLM LoRA + TTS, chosen by the pack | any language with a good STT and TTS | turn-based | 1× 24 GB per part | research |

---

## Recipe A — `lfm25-audio` (default, ship first)

**Base:** `LiquidAI/LFM2.5-Audio-1.5B` (Hugging Face). End-to-end audio–text model: FastConformer audio encoder → LFM2.5 1.2B backbone → depth transformer emitting Mimi codec tokens (8 codebooks, 24 kHz) → lightweight detokenizer. No separate ASR/TTS. GGUF builds exist for llama.cpp CPU inference; ONNX/WebGPU demos exist. A Japanese variant exists; broader multilingual output is announced — check current releases.

**Why first:** small enough for one 24 GB GPU (or two 4090s), upstream Python trainer (`liquid_audio` package), community full fine-tunes already demonstrate tool-aware voice flows trained in ~20 minutes on ~3k examples *(reported)*, and it deploys on CPU/edge.

**What it can learn from a few thousand turns:** workflow adherence, short tool acknowledgements, narrating injected tool results, refusals when a tool is missing, tone/style, accent and code-switch *understanding* (e.g. Indian English, Hinglish input).

**What it cannot learn cheaply:** a new output language on the English base checkpoint, factual knowledge, full-duplex behaviour.

**Locales:** `en-*` native; `hi-Latn-IN` understand_only; others unsupported until multilingual checkpoints ship.

**Data adapter:** each user turn → one training session: system text (persona + tool list + "Known facts you must use" block when the previous turn was a tool result) → user audio clip → assistant target (text + audio). Tool calls are represented as the text convention chosen for this recipe and parsed back at serve time. Keep a "no-tool chitchat" class in the mix so the model does not over-trigger tools.

**Training:** full fine-tune in bf16 via upstream trainer (LoRA via PEFT as an option if upstream supports it — verify). Defaults to start from: AdamW, lr 5e-5, cosine, ~50-step warmup, effective batch 8, 3–4 epochs, context ≈ 320 tokens *(reported starting point, tune on our eval)*.

**Hardware:** 1× 24 GB (batch 2–4) or 2× 24 GB DDP. Colab L4/A100 works.

**Eval focus:** tool-call accuracy by class, entity accuracy (names, IDs, amounts, dates per locale), ASR round-trip WER of generated speech, TTFA.

**Serve:** native streaming via `liquid_audio` for GPU; GGUF path via llama.cpp for CPU (verify audio-out support in the llama.cpp build you pin).

**Licence:** Liquid AI's model licence — read it before commercial use; document in `recipes/lfm25_audio/LICENSE_NOTES.md`.

**Known risks:** upstream API churn (the `liquid_audio` package is young); non-English text targets may degrade the English-centric speech decoder — measure.

---

## Recipe B — `moshi-lora` (advanced, full-duplex)

**Base options:**
- `kyutai/moshiko-pytorch-bf16` / `moshika` (Kyutai Moshi, 7B, CC-BY-4.0, English).
- `nvidia/personaplex-7b-v1` (Moshi architecture + weights, fine-tuned by NVIDIA for persona/voice control via text prompt + voice sample; code MIT, weights under NVIDIA Open Model License, gated on HF).

**Why:** the only open path to real interruptions, backchannels, and natural timing. PersonaPlex is the better starting point for agents because persona prompting already works; its documented gap is that the text prompt shapes persona only and does not carry content — which is exactly what domain fine-tuning addresses.

**Locales:** `en-*` native; `hi-Latn-IN` understand_only (measure); others unsupported. Kyutai has said multilingual variants are in development — revisit.

**Data requirement:** stereo dual-stream conversations (channel 0 user, channel 1 agent) with transcripts. Mono call recordings are not enough; `synth` can produce stereo, and `prepare` can reconstruct pseudo-stereo from diarized mono (lower quality; flagged).

**Training:** `kyutai-labs/moshi-finetune` (official, LoRA, includes dataset annotation tooling and a Colab). Pin a commit. Official example reports ~40 GB peak memory on one H100 for its recommended config *(reported)*. `nu-dialogue/moshi-finetune` (unofficial, Accelerate/DeepSpeed, trains the user stream too) is an alternative for multi-GPU; J-Moshi shows language transfer is possible but needed 69k hours and 128 GPUs — do not promise new-language support from this recipe.

**Adapter:** canonical stereo → moshi-finetune layout (stereo WAV + JSON transcript with timestamps). Verify exact JSON keys against the pinned commit.

**Eval focus:** everything in Recipe A plus duplex metrics: interruption response time, barge-in stop time, overlap rate vs human reference, false-interruption rate.

**Serve:** Moshi's own server (PyTorch/Rust) or vLLM-omni's PersonaPlex duplex serving; LiveKit has an experimental PersonaPlex plugin. Wrap one of these behind our Realtime-compatible WebSocket; mark which path is verified.

**Hardware:** 40–80 GB GPU for training; ~19 GB bf16 for inference *(reported)*, quantized ONNX variants exist.

**Licence notes:** CC-BY-4.0 (Moshi) vs NVIDIA Open Model License (PersonaPlex) — different obligations; surface at `vakforge train` time.

---

## Recipe D — `qwen-omni` (multilingual, Mandarin first)

**Base:** `Qwen/Qwen3-Omni-30B-A3B-Instruct` (MoE, ~3B active) or the current Qwen3.5-Omni release. Thinker–Talker architecture: the Thinker is a text/multimodal LLM (long context, tool calling via `<tool_call>` tags), the Talker turns its hidden states into streaming speech. Multilingual speech in and out including Mandarin; the only open native S2S family with function calling today. Weights are also on ModelScope (matters for users without Hugging Face access).

**Why:** unlocks non-English locale packs with native speech output, plus tool calling — the closest open analogue to GPT Realtime for global use.

**Locales:** `zh-CN` native; `en-*` native; `hi-Latn-IN`, `es`, `de`, `fr`, `ja`, `ar` — verify per language before marking native.

**Training approach:** *Thinker LoRA with Talker frozen*, via ms-swift (supports Qwen3-Omni). This teaches workflow, tool use, and understanding without touching speech generation. Talker adaptation (speaker fine-tune stage) is upstream's multi-stage pipeline and is *out of scope* until packaged. Known pitfall: Thinker-only checkpoints saved by some frameworks use a key layout the full model cannot load without re-keying and merging Talker/code2wav from the vanilla checkpoint — the adapter must handle this and test it.

**Adapter:** canonical → ms-swift multimodal chat JSONL (system, user audio, assistant text + tool calls). Audio-only training targets for the Thinker; speech output comes from the frozen Talker at inference.

**Hardware:** large. bf16 weights for the 30B-A3B are tens of GB; LoRA training realistically needs an 80 GB GPU or multi-GPU; inference via vLLM-omni. Measure and record before publishing numbers.

**Eval focus:** tool-call accuracy, entity accuracy per locale, intelligibility of Talker output in the target language (ASR round-trip with a locale STT), latency (near-duplex, expect higher than Moshi).

**Serve:** vLLM-omni (supports Qwen3-Omni); wrap behind the Realtime WS. Note that streaming audio support in local serving may lag the hosted API — verify and document what actually streams.

**Licence:** Apache-2.0 for Qwen3-Omni at time of writing — confirm for the exact checkpoint.

**Known risks:** framework version sensitivity (ms-swift/transformers/vLLM-omni move fast); hardware cost puts it out of reach for hobbyists — position it as the "team with a server" recipe.

---

## Recipe C — `cascade` (any language)

**Why:** for any locale without a good native speech-to-speech model, a cascade of fine-tunable open parts works today, and each part is independently trainable and swappable. The locale pack picks the parts.

**Components:**
- **STT:** Whisper fine-tune (transformers / Unsloth) as the default; pack overrides — AI4Bharat IndicConformer (NeMo) for Indic, Paraformer/SenseVoice for zh, NVIDIA Canary/Parakeet for en throughput.
- **LLM:** any small instruct model (3–8B, Qwen3/Gemma/Llama-class) with LoRA via Unsloth or LLaMA-Factory on chat records from the canonical manifest; tool calling in OpenAI shape.
- **TTS:** pack default — Indic Parler-TTS / IndicF5 for Indic, CosyVoice / Qwen3-TTS for zh, Orpheus / Sesame CSM / Kokoro-class for en; speaker fine-tune where the licence allows.
- **Orchestration:** Pipecat pipeline with sentence-boundary aggregation; VAD for turn-taking.

**Data:** public corpora chosen by the pack (Common Voice, AI4Bharat Vistaar/IndicVoices, WenetSpeech, etc.) plus your domain data.

**Eval focus:** STT WER/CER by language and entity type; LLM tool-call accuracy; end-to-end task completion; total latency (the cascade's weakness).

**Hardware:** 1× 24 GB for each component's fine-tune; inference fits on one GPU.

---

## Considered, not (yet) a recipe

- **Step-Audio2, MiniCPM-o 4.5, GLM-4-Voice, LLaMA-Omni2:** track; add when an end-to-end run is validated.
- **Ultravox:** speech-in, text-out with a published training pipeline — a good STT+LLM replacement inside the cascade, not a standalone S2S recipe.
- **Talker / speaker fine-tuning for Qwen-Omni:** when upstream packages it.

## Adding a recipe (checklist)

1. Implements `Recipe` and `Adapter` protocols (`ARCHITECTURE.md`).
2. Optional extra in `pyproject.toml`; lazy imports; `check_env()` reports missing pieces clearly.
3. Unit tests on CPU with fixtures; one `@pytest.mark.model` integration test.
4. Config YAML with documented defaults.
5. Ran end to end on a public demo dataset; `report.md` committed under `benchmarks/`.
6. `LICENSE_NOTES.md` for the base model.
7. Per-locale support declared in each launch pack.
8. Section in this file and a row in `README.md`.
