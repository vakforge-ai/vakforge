# Evaluation and serving

The point is not "we fine-tuned it" but "it got better on the user's held-out data". `eval`
always scores base and tuned on the same test split and emits one report. No metric without
its baseline. Full text: `docs/EVALUATION.md`, `docs/ARCHITECTURE.md`.

## Test split

Held out by conversation and by speaker; never seen by training or by synth prompt examples.
Stratified by locale, audio condition (clean, phone, noisy), primary language and source
(real, synthetic). Minimum 100 turns for a headline number; fewer gets a "low-n" badge and a
bootstrap confidence interval.

## Metrics

| Group | Metric | How |
|---|---|---|
| recognition | WER / CER | `jiwer` after the pack's `normalize_text` (case, punctuation, numbers, currency, dates, script); CER is the headline for Chinese and Japanese; report raw and normalized |
| recognition | entity accuracy | exact match on `entities[]` by type; usually the number that decides whether a business agent is usable |
| recognition | code-switch WER | WER on turns whose `lang_mix` has more than one language |
| behaviour | tool-call accuracy | per class: right tool with valid args, correct refusal when no tool fits, no spurious call, correct narration of a tool result; args checked by JSON Schema plus exact match on required fields |
| behaviour | task completion | scripted multi-turn scenarios with a checklist; rules where possible, else an LLM judge with a rubric whose model and prompt hash go in the report |
| behaviour | hallucination rate | given the tools' returned facts, does the spoken answer contradict or invent; judge plus a 30-item human sample |
| behaviour | instruction adherence | persona and system-prompt constraints, rubric judge |
| speech | intelligibility | ASR round-trip: transcribe generated audio with a fixed reference ASR, WER against the model's own text |
| speech | voice similarity | cosine similarity of speaker embeddings against the target voice, only when a voice target exists |
| latency | TTFT / TTFA, total, real-time factor | measured on the serving path, p50 and p95, hardware recorded |
| duplex | barge-in stop time, interruption response time, false-interruption rate, overlap rate | `moshi-lora` only |

Robustness: every metric re-run on augmented copies of the test split (phone band-pass,
+10/+20 dB babble, reverb). Report degradation, not just clean numbers.

## Report shape

`runs/<timestamp>/report.md` and `report.json`, in this order: summary table (base → tuned,
delta, CI, n); top 5 improvements and top 5 regressions by slice; breakdowns by locale,
condition, language, source, entity type, tool class; latency table with hardware; 10 paired
samples with audio links; provenance (manifest hash, config, versions, judge hashes, seed).

Ship only if the summary shows the tuned model better on the metrics `recommend` named,
with regressions inside a budget the user agreed to.

## Serving: open model, standard wire format

The model backend implements:

```python
class StreamingBackend(Protocol):
    async def append_audio(self, pcm16: bytes) -> None: ...
    async def commit(self) -> None: ...
    async def responses(self) -> AsyncIterator[RealtimeEvent]: ...
    async def tool_result(self, call_id: str, content: dict) -> None: ...
```

The first front end speaks the OpenAI Realtime WebSocket format, so existing clients change
one URL. Documented subset:

- client → server: `session.update`, `input_audio_buffer.append`, `input_audio_buffer.commit`, `input_audio_buffer.clear`, `response.create`, `response.cancel`, `conversation.item.create` (for `function_call_output`)
- server → client: `session.created`, `input_audio_buffer.speech_started/stopped`, `response.created`, `response.audio.delta`, `response.audio_transcript.delta`, `response.function_call_arguments.done`, `response.done`, `error`
- audio: PCM16, 24 kHz, base64

Unsupported events return a structured `error` naming the event. Ship a `serve/README.md`
listing exactly which events are supported, a 50-line Python client, and a Dockerfile (CPU
and CUDA). WebRTC (LiveKit, Pipecat) and SIP front ends plug into the same backend later.

Run directory for every training or serving run:

```
runs/<timestamp>_<recipe>/
  config.yaml          # fully resolved
  manifest_hash.txt
  versions.txt         # pip freeze of the recipe environment
  train.log
  checkpoint/
  report.md / report.json
```
