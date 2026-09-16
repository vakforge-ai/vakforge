# Canonical data format — `vakforge.jsonl`

One JSON object per line, one **conversation** per object. Every recipe reads this format through an adapter (`vakforge/adapters/<recipe>.py`); no recipe reads raw user data directly. The pydantic models in `vakforge/schema.py` are the source of truth; this document explains intent.

## Design goals

- Model-agnostic: works for turn-based S2S, full-duplex S2S, and cascaded STT→LLM→TTS.
- Time-aligned: every turn has start/end so we can cut audio, build stereo streams, and score interruptions.
- Code-switch aware: language per turn, not per file.
- Tool-aware: tool calls and results are first-class, in the same shape the serving layer will emit.
- Provenance-aware: consent, licence, source (real/synthetic), and redaction status travel with every row.

## Layout on disk

```
my-agent/
  data/
    raw/                    # untouched user uploads (never modified, git-ignored)
    audio/                  # normalized 24 kHz WAVs produced by `prepare`
    vakforge.jsonl          # canonical manifest
    vakforge.schema.json    # exported JSON Schema (for external validators)
    splits.json             # conversation ids per split
```

## Record

```json
{
  "id": "conv_000123",
  "schema_version": "0.1",

  "audio": {
    "path": "audio/conv_000123.wav",
    "sample_rate": 24000,
    "channels": 2,
    "channel_map": {"0": "user", "1": "agent"},
    "duration_s": 47.3,
    "condition": "phone"
  },

  "locale": "hi-Latn-IN",
  "language": {
    "primary": "hi-Latn",
    "mix": ["hi", "en"]
  },

  "domain": "field_service_support",
  "scenario": "book_site_visit",

  "system_prompt": "You are Priya from SunCare Solar support. Verify the customer, check the ticket, book a visit if needed. Speak Hinglish if the customer does.",

  "tools": [
    {
      "name": "book_appointment",
      "description": "Book a technician visit",
      "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "date": {"type": "string", "format": "date"}, "slot": {"type": "string", "enum": ["morning", "afternoon"]}}, "required": ["customer_id", "date", "slot"]}
    }
  ],

  "turns": [
    {"speaker": "agent", "start": 0.0, "end": 2.8, "text": "Namaste, SunCare Solar se Priya bol rahi hoon. Kaise madad kar sakti hoon?", "lang": "hi-Latn"},
    {"speaker": "user", "start": 2.9, "end": 7.4, "text": "Haan, mera inverter kal se off hai, customer ID SC-4471.", "lang": "hi-Latn", "entities": [{"type": "customer_id", "text": "SC-4471", "start_char": 44, "end_char": 51}]},
    {"speaker": "agent", "start": 7.2, "end": 8.1, "text": "Ek minute, check karti hoon.", "lang": "hi-Latn", "overlap": true},
    {"speaker": "agent", "start": 8.1, "end": 8.1, "tool_call": {"id": "call_1", "name": "check_status", "arguments": {"customer_id": "SC-4471"}}},
    {"speaker": "tool", "start": 8.1, "end": 8.1, "tool_result": {"id": "call_1", "content": {"status": "fault_reported", "last_service": "2026-06-02"}}},
    {"speaker": "agent", "start": 8.4, "end": 13.9, "text": "Ji, fault already logged hai. Kal subah ka slot book kar doon? Charge ₹500 hoga.", "lang": "hi-Latn", "entities": [{"type": "amount_inr", "text": "₹500", "normalized": 500}]},
    {"speaker": "user", "start": 14.0, "end": 15.2, "text": "Haan theek hai.", "lang": "hi-Latn"},
    {"speaker": "agent", "start": 15.3, "end": 15.3, "tool_call": {"id": "call_2", "name": "book_appointment", "arguments": {"customer_id": "SC-4471", "date": "2026-09-17", "slot": "morning"}}}
  ],

  "meta": {
    "source": "real",
    "consent": "recorded_verbal",
    "consent_ref": "policy-v3-2026",
    "license": "proprietary-internal",
    "pii_redacted": true,
    "redaction_log": "redactions/conv_000123.json",
    "transcription": {"engine": "faster-whisper-large-v3", "verified_by_human": false},
    "diarization": {"engine": "channels", "confidence": 1.0},
    "split": "train",
    "created": "2026-09-16T10:12:00Z"
  }
}
```

## Field notes

**audio.channels / channel_map** — `2` with a channel map means true dual-stream audio (required by `moshi-lora`). `1` means mixed mono; turns then come from diarization and `adapters/moshi.py` will refuse it unless `--allow-synthetic-stereo` reconstructs streams from cut segments (lower quality; flagged in the report).

**audio.condition** — `studio | clean | phone | noisy`. Set by `inspect` heuristics, overridable. Used to stratify eval.

**locale** — id of the locale pack that governs normalization, entity types, PII rules, and benchmark assignment for this conversation (`en-US`, `en-GB`, `en-IN`, `hi-Latn-IN`, `zh-CN` …). A project may mix locales; eval always breaks down by it.

**language.primary** — BCP-47. Examples: `en-US`, `en-GB`, `en-IN`, `hi-Latn` (Roman Hindi), `hi` (Devanagari), `zh-CN`. `mix` lists every language present in the conversation.

**turns[].lang** — required on every spoken turn. `prepare` sets it via the locale pack's `detect_lang` after transcription, because ASR language IDs are unreliable on code-switched speech (Hinglish, Spanglish, Chinese–English).

**turns[].overlap** — `true` when this turn starts before the previous one ends. Duplex eval uses it; turn-based adapters drop or merge such turns and log how many.

**turns[].tool_call / tool_result** — OpenAI-style function-calling shape so the same records drive training and serving. A tool call turn has zero duration; a `speaker: "tool"` turn carries the result.

**turns[].entities** — optional but strongly recommended for business data: `customer_id`, `phone`, `amount_inr`, `date`, `person_name`, `address`, `order_id`. Entity accuracy is one of the headline eval metrics.

**meta.source** — `real | synthetic | public`. Never mix without this tag; eval reports break results down by source.

**meta.consent** — `recorded_verbal | written | synthetic | public_license | none`. `none` is allowed only with `--allow-unconsented` and is excluded from any published artifact. See `DATA_ETHICS.md`.

**meta.pii_redacted** — `prepare` refuses to write `train` rows with `false` unless `--skip-redaction` is set, which logs a loud warning.

## Splits

Split by conversation id **and** ensure no speaker (agent voice or, where known, customer) appears in more than one split. `splits.json` records the assignment and the seed so evaluation is reproducible.

## Adapters

| Recipe | Adapter output |
|---|---|
| `lfm25-audio` | List of chat sessions: system text (prompt + tools), user audio clip per user turn (cut from `audio.path` using start/end), assistant target = interleaved text + audio tokens, tool-call turns rendered as the text convention the recipe defines. |
| `moshi-lora` | Directory of stereo WAVs + per-file JSON transcripts with word/turn timestamps in the layout `moshi-finetune` expects (verified against the pinned commit). |
| `qwen-omni` | ms-swift multimodal chat JSONL: system, user audio, assistant text and tool calls (Thinker targets only; Talker frozen). |
| `cascade` | STT pairs `(user_clip.wav, text)`; LLM chat records `(system, history, assistant_text_or_tool_call)`; TTS pairs `(agent_clip.wav, text)`. Engines chosen by the locale pack. |

Adapters must be pure functions of the manifest plus config, and must write a `manifest_hash` into their output so training runs are traceable to exact data.

## Validation rules (implemented in `vakforge validate`)

- `locale` names a registered pack; every `turns[].lang` is one the pack (or a sibling pack in the project) declares.
- Every `audio.path` exists, decodes, matches declared sample rate/channels/duration ±0.5 s.
- Turns are sorted by `start`; `end >= start`; spoken turns have non-empty `text` and `lang`.
- Tool call ids are unique within a conversation and every `tool_result` references an existing call.
- `tools[].parameters` is valid JSON Schema; tool call arguments validate against it.
- Split assignments are complete and leak-free.
- `meta.consent != "none"` or explicit override.

Errors point at `id`, turn index, and field, and suggest the fix.
