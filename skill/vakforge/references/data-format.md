# Canonical data format: `data/vakforge.jsonl`

One JSON object per line, one conversation per object. Every recipe reads this through an
adapter; nothing reads raw user data directly. `vakforge schema` exports the JSON Schema;
`vakforge validate <file>` checks a manifest and names the field to fix.

## Record

```json
{
  "id": "conv_000123",
  "schema_version": "0.1",
  "audio": {"path": "audio/conv_000123.wav", "sample_rate": 24000, "channels": 2,
            "channel_map": {"0": "user", "1": "agent"}, "duration_s": 47.3, "condition": "phone"},
  "locale": "hi-Latn-IN",
  "language": {"primary": "hi-Latn", "mix": ["hi", "en"]},
  "domain": "field_service_support",
  "scenario": "book_site_visit",
  "system_prompt": "You are Priya from SunCare Solar support. ...",
  "tools": [{"name": "book_appointment", "description": "...", "parameters": {"type": "object", "...": "..."}}],
  "turns": [
    {"speaker": "agent", "start": 0.0, "end": 2.8, "text": "Namaste, ...", "lang": "hi-Latn"},
    {"speaker": "user", "start": 2.9, "end": 7.4, "text": "...", "lang": "hi-Latn",
     "entities": [{"type": "customer_id", "text": "SC-4471", "start_char": 44, "end_char": 51}]},
    {"speaker": "agent", "start": 8.1, "end": 8.1,
     "tool_call": {"id": "call_1", "name": "check_status", "arguments": {"customer_id": "SC-4471"}}},
    {"speaker": "tool", "start": 8.1, "end": 8.1,
     "tool_result": {"id": "call_1", "content": {"status": "fault_reported"}}}
  ],
  "meta": {"source": "real", "consent": "recorded_verbal", "consent_ref": "policy-v3-2026",
           "license": "proprietary-internal", "pii_redacted": true,
           "redaction_log": "redactions/conv_000123.json",
           "transcription": {"engine": "faster-whisper-large-v3", "verified_by_human": false},
           "diarization": {"engine": "channels", "confidence": 1.0},
           "split": "train", "created": "2026-09-16T10:12:00Z"}
}
```

## Rules the validator enforces

- `audio` is optional: records built from documents, tables or chats have none until synth renders it. Stereo (`channels: 2`) needs `channel_map`; channel 0 is the user, channel 1 the agent. Audio is 24 kHz.
- `locale` names a registered pack; every spoken turn has non-empty `text` and a `lang` the pack declares. `prepare` sets `lang` with the pack's `detect_lang` after transcription, because speech-to-text language IDs are unreliable on code-switched speech.
- Turns are sorted by `start`, `end >= start`. `overlap: true` when a turn starts before the previous one ends; turn-based adapters drop or merge such turns and log how many.
- Tool calls use the OpenAI function-calling shape so the same rows drive training and serving. A tool-call turn has zero duration, `speaker: "agent"`, a unique `id`, and a name declared in `tools`. A `speaker: "tool"` turn carries the result and references an existing call. Arguments validate against `tools[].parameters`.
- `entities` are optional but drive the entity-accuracy metric: `customer_id`, `phone`, `amount_*`, `date`, `person_name`, `address`, `postal_code`, `order_id`.
- `meta.source` ∈ `real | synthetic | public`; eval always breaks results down by it.
- `meta.consent` ∈ `recorded_verbal | written | synthetic | public_license | none`. `none` needs `--allow-unconsented` and is never exported.
- `meta.pii_redacted` must be true for `train` rows unless `--skip-redaction` was passed, which logs a warning on every run.
- Splits: by conversation id and by speaker, recorded in `splits.json` with the seed. No speaker appears in two splits.

## Adapter targets (what `train/` produces from the manifest)

| Recipe | Adapter output |
|---|---|
| `lfm25-audio` | chat sessions: system text (prompt + tools + "known facts" block after a tool result), user audio clip cut by start/end, assistant target as interleaved text and audio; tool calls rendered in the recipe's text convention; keep a no-tool chitchat class |
| `moshi-lora` | stereo WAVs plus per-file JSON transcripts with timestamps in the layout the pinned `moshi-finetune` commit expects (read it first) |
| `qwen-omni` | ms-swift multimodal chat JSONL: system, user audio, assistant text and tool calls; Thinker targets only, Talker frozen |
| `cascade` | STT pairs (user clip, text); LLM chat records; TTS pairs (agent clip, text); engines from the locale pack |

Adapters are pure functions of manifest plus config and write a `manifest_hash` so every
run is traceable to exact data.
