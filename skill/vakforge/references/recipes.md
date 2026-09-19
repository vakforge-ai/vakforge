# Recipes: pitfalls per base model

Facts here were checked in September 2026. **Re-verify upstream versions, APIs and licences
in the installed source before writing a line of glue**, and tell the user what you verified
and where. Anything marked *(reported)* comes from third-party write-ups and must be measured
before you repeat it as fact. Full text: `docs/RECIPES.md`.

## Verify-first checklist (every recipe)

1. `pip show <package>` and `python -c "import x; print(x.__file__)"`; read the trainer's entry point, its dataset loader and its config schema.
2. Pin the exact version or commit in the project's `pyproject.toml`. Model libraries pin conflicting `torch` and `transformers` versions; keep each recipe in its own optional extra or environment.
3. Confirm the base checkpoint name, its licence and whether it is gated on Hugging Face. Gated weights (pyannote, PersonaPlex) need the user to accept terms; document the step, never bundle weights.
4. Write the adapter as a pure function with a CPU test on a synthetic fixture before any GPU time.

## `lfm25-audio` (default, ship first)

- Base: `LiquidAI/LFM2.5-Audio-1.5B`. Audio in, audio and text out; no separate STT/TTS. GGUF builds exist for CPU inference.
- Learns from a few thousand turns: workflow, tool acknowledgements, narrating tool results, refusals, tone, accent and code-switch *understanding*.
- Cannot learn cheaply: a new output language, facts, full-duplex behaviour.
- Locales: English native; Hinglish `understand_only` (speech out stays English).
- Adapter: one training session per user turn: system text (persona, tool list, "known facts" block after a tool result), user audio clip, assistant target as interleaved text and audio. Tool calls in a text convention you define and parse back at serve time. Keep a no-tool chitchat class.
- Training: upstream `liquid_audio` trainer, bf16; starting point *(reported)*: AdamW, lr 5e-5, cosine, ~50 warm-up steps, effective batch 8, 3 to 4 epochs. One 24 GB GPU or Colab L4/A100.
- Risks: the `liquid_audio` package is young and its API moves; non-English text targets may degrade the English-centric speech decoder, so measure.

## `moshi-lora` (full-duplex)

- Base: `kyutai/moshiko-pytorch-bf16` or `moshika` (CC-BY-4.0), or `nvidia/personaplex-7b-v1` (NVIDIA Open Model License, gated; persona via text prompt and voice sample). Surface the licence difference at train time.
- Only open path to real interruptions, backchannels and natural timing. English.
- Data: stereo, user on channel 0 and agent on channel 1, with transcripts. Mono is not enough; pseudo-stereo from diarized mono is lower quality and must be flagged in the report.
- Training: `kyutai-labs/moshi-finetune`, LoRA; pin a commit and read its dataset JSON keys before writing the adapter. ~40 GB peak on one H100 for the reference config *(reported)*. Do not promise new-language support: J-Moshi needed 69k hours and 128 GPUs.
- Eval adds duplex metrics: barge-in stop time, interruption response time, false-interruption rate, overlap rate versus the human reference.

## `qwen-omni` (multilingual, Mandarin first)

- Base: `Qwen/Qwen3-Omni-30B-A3B-Instruct` or the current Qwen3.5-Omni release; Thinker (text, tool calling) plus Talker (speech). Also on ModelScope for users without Hugging Face access.
- Approach: Thinker LoRA with Talker frozen via ms-swift. Talker fine-tuning is out of scope until upstream packages it.
- Pitfall: Thinker-only checkpoints saved by some frameworks cannot be loaded by the full model without re-keying and merging Talker/code2wav from the vanilla checkpoint. The adapter must handle this and test the round trip.
- Hardware: an 80 GB GPU or multi-GPU for LoRA; serve via vLLM-omni. Verify what actually streams in local serving; it may lag the hosted API.

## `cascade` (any language)

- Speech-to-text fine-tune (Whisper via transformers or Unsloth; the locale pack may override: IndicConformer for Indic, Paraformer for Chinese) plus a small instruct LLM with LoRA (Unsloth or LLaMA-Factory) with OpenAI-shape tool calling, plus the pack's TTS (Indic Parler-TTS or IndicF5 for Indic, CosyVoice for Chinese, Orpheus/Kokoro-class for English), orchestrated with Pipecat.
- Each part trains and swaps independently; latency is the weakness. One 24 GB GPU per component.
- Whisper-family models mislabel Roman Hindi as English or Hindi inconsistently: always run the pack's `detect_lang` after transcription.

## Considered, not recipes

Step-Audio2, MiniCPM-o, GLM-4-Voice, LLaMA-Omni2: track, add when an end-to-end run is
validated. Ultravox: speech-in text-out, a good STT+LLM replacement inside the cascade, not a
standalone recipe.
