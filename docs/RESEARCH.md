# Research behind the decisions

Every threshold in `vakforge recommend` and every claim in `docs/DECISION_GUIDE.md` should
either cite evidence or admit it is a heuristic. This file is the record: what the literature
says, what we changed because of it, and what we still cannot support.

Scope: published work through September 2026, gathered across several independent searches of
the speech, dialogue and privacy literature. Where sources disagreed, the disagreement is
recorded rather than averaged.

**How to read the confidence column.** *Verified* means we checked the primary source
ourselves. *Measured* means at least one cited paper reports the number from an experiment.
*Reported* means a model team stated it without independent replication. *Heuristic* means we
chose it and no evidence supports or refutes it; it stays only if the CLI says so.

## What changed because of this

| Decision | Was | Now | Confidence | Evidence |
|---|---|---|---|---|
| Fine-tune to add company facts | allowed | never; retrieval only | Measured | Ovadia et al. 2024 (arXiv 2312.05934): retrieval beat unsupervised fine-tuning for both existing and new facts. Gekhman et al. 2024 (arXiv 2405.05904): fitting new-knowledge examples raises hallucination roughly linearly |
| Behaviour fine-tune target: 600 turns | presented as a data requirement | a staged heuristic, labelled as such; quality and branch coverage matter more than count | Heuristic | LIMA (arXiv 2305.11206): 1,000 curated examples suffice for style and format. Spec-TOD (arXiv 2507.04841): ~840 dialogues competitive on MultiWOZ. Neither validates 600 or 200 |
| Tool-use fine-tune: covered by the same 600 turns | same as behaviour | separate and much larger; prompt and schema first | Measured | Published tool-learning corpora run 8k to 60k examples (BUTTONInstruct 8k, APIGen 60k, ToolACE 26,507 APIs). Hundreds of examples suit one fixed tool, not general multi-turn tool use |
| Duplex fine-tune: 10 hours of calls | enough to train duplex behaviour | nowhere near; duplex mechanics are a base-model property, not something 10 hours teaches | Verified | PersonaPlex: ~1,217 h real Fisher telephone audio plus 2,250+ h synthetic. Moshi (arXiv 2410.00037): thousands of hours of stereo dialogue over a 7M-hour pretrained base. 10 h is light persona adaptation on top of an already-duplex model, at most |
| Voice cloning: 10 hours | same threshold as duplex | seconds to minutes | Measured | VALL-E (arXiv 2301.02111) clones from a 3-second prompt; YourTTS fine-tunes a speaker in under a minute |
| ASR accent and entity adaptation: ~10 hours | unstated | defensible floor, keep, but try contextual biasing first | Measured | 20 h of Indian-accented data took WER from 22.24% to 8.33% (arXiv 2409.11107). Prompt biasing cuts entity errors 18 to 50% with no training at all (arXiv 2506.06252, 2505.19179) |
| Qwen-Omni for Hindi speech output | marked "verify" | unsupported, and the pack already says so | Verified | Qwen3-Omni model card: speech output is English, Chinese, French, German, Russian, Italian, Spanish, Portuguese, Japanese, Korean. Hindi absent, and absent from speech input too |
| Word error rate as the headline metric | implied | diagnostic only; task completion, entity accuracy and tool-call accuracy lead | Measured | Sarikaya et al. 2003: a recogniser with 46% higher WER had up to 17% lower slot error. SpokenWOZ (NeurIPS 2023): 6.1% WER yet 25.65% joint-goal accuracy |
| Roman-Hindi WER scoring | unstated | script-normalised WER, applied identically to reference and hypothesis; never the stock Whisper normaliser on Indic text | Measured | The Whisper non-English normaliser strips Devanagari vowel signs. Transliteration-normalised WER (Emond et al., SLT 2018) and script-normalised WER are the standard fixes |
| Synthetic dialogues can carry a locale | implied | synthetic teaches coverage and structure; natural data is required for natural code-switching, and the test set stays real | Measured | CS-YODAS: natural code-switched training moved Hindi-English accuracy from 0% to 19.9%, where synthetic alone failed. PersonaPlex mixes roughly 65% synthetic with 35% real |
| PII redaction: text is enough | implied | text plus time-aligned audio; measure end-to-end recall, not transcript F1 | Measured | Baril et al. 2022 (arXiv 2204.12622): transcript NER recall ~0.96 but the end-to-end French audio pipeline reached only 0.631 recall |
| Fine-tuned voice models are safe once text is scrubbed | assumed | assume leakage; speaker identity is extractable from fine-tuned TTS | Measured | Membership-inference on fine-tuned TTS reports speaker-level AUC above 0.80. Carlini et al. 2021 established verbatim extraction from language models |

## Where the sources disagreed

- **Hinglish speech recognition numbers.** One comparison puts Whisper at 36.2% word error
  rate against IndicWhisper at 29.5%, but it is not peer reviewed. The clearest published
  Hindi-English figure found is 21.77% from a wav2vec2 system, and no controlled study
  establishes how often Whisper mislabels Hinglish. Treat all of these as indicative. vakforge
  should tell users to run their own comparison on their own audio rather than quote a number.
- **Language identification accuracy.** A cited "94.5% for Hinglish" traces to a paper about
  a mobile-keyboard language-detection engine, not Hinglish speech. Word-level identification
  on Roman Hindi text is well supported (F1 around 0.95 to 0.98); per-utterance identification
  on speech is not the same task.
- **Per-utterance language labels.** There is a good argument that a single label per turn is
  the wrong primitive for Hinglish, and that token-level tags plus a code-mixing score are
  needed. Our schema already carries both a primary language and a mix list, so this is a gap
  in the detector, not the format.

## What nobody could support

- **A universal "fraction of the gap closed by prompt plus retrieval".** Measured effects
  range from retrieval beating fine-tuning outright to modest gains. Report the baseline per
  project; never quote a percentage.
- **Training memory and wall-clock time per recipe.** No reproducible comparison exists across
  LFM2.5-Audio, Moshi, PersonaPlex and Qwen-Omni for company-scale adaptation. `docs/RECIPES.md`
  keeps these as unverified until we measure them.
- **Personal-data memorisation by fine-tuned speech recognition or speech-to-speech models.**
  No published measurement. Treat as an unquantified risk and redact before training.
- **A single acceptable latency threshold.** One academic study puts acceptability under about
  2 seconds; Moshi reports about 200 ms model latency. Report p50 and p95 per project instead
  of a pass mark.
- **Hindi personal-data detection quality.** The best published multilingual system reports
  Hindi precision 0.781, recall 0.628. Our Aadhaar and PAN patterns use checksums, which is
  stronger for those specific identifiers, but names remain the weak point.

## Rules this gives us

1. **Retrieval first, always.** Facts go to retrieval and tools. Fine-tuning changes behaviour,
   format, tone and tool selection. This is the most strongly supported finding in the whole
   review and it is the product's core claim.
2. **Quote evidence, not thresholds.** `recommend` reports what the data supports and what the
   literature says the route needs, and labels its own numbers as heuristics.
3. **Duplex is a model choice, not a training budget.** Pick a model that is already full-duplex,
   then adapt lightly. Never tell a user that 10 hours buys duplex behaviour.
4. **Measure the baseline before training.** Contextual biasing and prompt plus retrieval close
   much of the gap for free, and the baseline is the only thing that proves training was needed.
5. **Keep the evaluation set real.** Synthetic data is for coverage. Shipping decisions use real
   calls with real accents and real interruptions.

## Reading list

1. Ovadia et al. 2024, *Fine-Tuning or Retrieval?* (arXiv 2312.05934)
2. Gekhman et al. 2024, *Does Fine-Tuning LLMs on New Knowledge Encourage Hallucinations?* (arXiv 2405.05904)
3. Défossez et al. 2024, *Moshi* (arXiv 2410.00037)
4. Lin et al. 2025, *Full-Duplex-Bench* (arXiv 2503.04721)
5. Baril et al. 2022, *Named Entity Recognition for Audio De-Identification* (arXiv 2204.12622)

## Caution

Not every entry here was read end to end; some come from abstracts and secondary summaries.
One citation met during the search pointed at the wrong paper, and vendor-blog numbers sit
next to peer-reviewed results in ordinary search output, so both were kept out of the tables
above. Claims marked *Verified* were checked against the primary source. Check the source
before repeating any other claim publicly, in the README, on the site or in a talk.
