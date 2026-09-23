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
     "entities": [{"type": "customer_id", "text": "SC-4471", "start_char": 48, "end_char": 55}]},
    {"speaker": "agent", "start": 8.1, "end": 8.1,
     "tool_call": {"id": "call_1", "name": "check_status", "arguments": {"customer_id": "SC-4471"}}},
    {"speaker": "tool", "start": 8.1, "end": 8.1,
     "tool_result": {"id": "call_1", "content": {"status": "fault_reported"}}}
  ],
  "meta": {"source": "real", "consent": "recorded_verbal", "consent_ref": "policy-v3-2026",
           "voice_consent_ref": "voice-consent-v1-2026",
           "license": "proprietary-internal", "pii_redacted": true,
           "redaction_log": "redactions/conv_000123.json",
           "transcription": {"engine": "faster-whisper-large-v3", "verified_by_human": false},
           "diarization": {"engine": "channels", "confidence": 1.0},
           "split": "train", "created": "2026-09-16T10:12:00Z"}
}
```

## Rules the validator enforces

- `audio` is optional: records built from documents, tables or chats have none until synth renders it. Stereo (`channels: 2`) needs `channel_map` assigning one channel to `user` and the other to `agent`; the convention is channel 0 user, channel 1 agent. Audio is 24 kHz. `audio.path` is relative to the manifest — absolute paths and `..` are rejected.
- `locale` names a registered pack; every spoken turn has non-empty `text` and a `lang` the pack declares. `prepare` sets `lang` with the pack's `detect_lang` after transcription, because speech-to-text language IDs are unreliable on code-switched speech.
- Turns are sorted by `start`, `end >= start`. `overlap: true` when a turn starts before the previous one ends; turn-based adapters drop or merge such turns and log how many.
- Tool calls use the OpenAI function-calling shape so the same rows drive training and serving. A tool-call turn has zero duration, `speaker: "agent"`, a unique `id`, and a name declared in `tools`. A `speaker: "tool"` turn carries the result and references an existing call. Arguments validate against `tools[].parameters`.
- `entities` are optional but drive the entity-accuracy metric: `customer_id`, `phone`, `amount_*`, `date`, `person_name`, `address`, `postal_code`, `order_id`. Offsets are optional; when given, both are required and `text[start_char:end_char]` must equal the entity's `text`.
- `meta.source` ∈ `real | synthetic | public`; eval always breaks results down by it.
- `meta.consent` ∈ `recorded_verbal | written | synthetic | public_license | none`. `none` needs `--allow-unconsented` and is never exported.
- Provenance claims must carry evidence, or the record fails: `recorded_verbal`/`written` need `consent_ref`, `public_license` needs `license`, `synthetic` consent needs `synthetic` source. `source: real` needs `pii_redacted: true` **and** a `redaction_log`, and `validate` re-scans the text to prove that claim rather than trusting it.
- `meta.allowed_uses` says what the row may be trained for (`asr`, `workflow`, `evaluation`, `voice_clone`), defaulting to the three ordinary uses. Adding `voice_clone` to real audio requires `voice_consent_ref`: consent to record a call is not consent to reproduce the caller's voice.
- Duplicate tool names are rejected: two schemas under one name make every call to it ambiguous.
- Splits: by conversation id and by speaker, recorded in `splits.json` with the seed. `validate` can only check the conversation half — the format carries no speaker identity — so keeping a speaker out of two splits is your pipeline's job, and it should record how it did it.

## Adapter targets (what `train/` produces from the manifest)

| Recipe | Adapter output |
|---|---|
| `lfm25-audio` | chat sessions: system text (prompt + tools + "known facts" block after a tool result), user audio clip cut by start/end, assistant target as interleaved text and audio; tool calls rendered in the recipe's text convention; keep a no-tool chitchat class |
| `moshi-lora` | stereo WAVs plus per-file JSON transcripts with timestamps in the layout the pinned `moshi-finetune` commit expects (read it first) |
| `qwen-omni` | ms-swift multimodal chat JSONL: system, user audio, assistant text and tool calls; Thinker targets only, Talker frozen |
| `cascade` | STT pairs (user clip, text); LLM chat records; TTS pairs (agent clip, text); engines from the locale pack |

Adapters are pure functions of manifest plus config and write a `manifest_hash` so every
run is traceable to exact data.
