# Glossary

The words `vakforge inspect` and `vakforge recommend` use, and the fields they write to `inspect.json` and `recommend.json`. The [decision guide](DECISION_GUIDE.md) explains how the decisions are made; this page says what each term means.

## Reading your data (`inspect`)

**Source kinds.** Every file is sorted into one of five kinds:

| Kind | What it is | Read from |
|---|---|---|
| document | Text to look facts up in | Markdown, text, HTML, reStructuredText, and FAQ files |
| table | Records with columns | CSV, TSV, SQL dumps, JSON, JSONL |
| chat | Conversations | WhatsApp exports, JSON/JSONL chat logs, CSV/JSON with one exchange or one message per row |
| audio | Recordings | WAV, FLAC, OGG, Opus (WhatsApp voice notes), MP3 |
| other | Anything else | Listed, not read |

**Found and profiled.** *Found* (`counts`) is every file in the folder; *profiled* (`profiled`) is the ones that were actually read. Every other total comes from profiled files only, so the two numbers together say how much of the folder the report covers.

**Skipped.** A file vakforge found but cannot read yet, listed with the reason and what to do: a PDF or Word file ("text extraction not in core yet"), an Excel workbook ("export to CSV"), an `.m4a` recording ("convert to WAV or FLAC").

**Truncated.** A file read only up to a limit: 2 million characters of text, or 32 million for a JSON document, which has to be read whole. Its counts cover the part that was read. The CLI marks it `partial`.

**Sampled.** A large file is counted in full, but its personal data and languages are judged from the start of it. `rows_scanned` (tables) and `messages_scanned` (chats) say how much was scanned; the CLI adds "(large files sampled)".

**Message.** One thing one person said in a chat: a WhatsApp message with any lines it runs onto, one record of a chat log, or one side of an exchange.

**Turn.** A message counted as training data. The bars for behaviour, tools and language are measured in turns. For language, only the turns that are not in English count, estimated from the share of sampled text that is not English. A recording is not turns until it has been transcribed and split by speaker, which `inspect` does not do.

**Exchange.** A row with a user column and a reply column, such as `input`/`output`, `instruction`/`response`, `customer`/`agent` or `user`/`assistant`. Each exchange is two messages. A file of one message per row instead has a speaker column (`role`, `speaker`, `from`, …) and a text column (`text`, `message`, `content`, …).

**FAQ file.** A CSV or JSON file with `question` and `answer` columns. It holds facts, so it is read as a document and routed to retrieval, not to a fine-tune. `faq_pairs` counts its pairs.

**ID column.** A column that identifies a record, such as `order_id`, `Ticket ID`, `sku` or `customer_id`, however the export spells it.

**Tool candidate.** A lookup the assistant could call, made from a table and one of its ID columns: `lookup_orders_by_order_id`. Tools answer questions about records ("where is my order?") without training anything.

**Personal data (PII).** What `inspect` found that identifies a person. Most of it is matched by the locale pack's patterns: email, phone, payment card (checked with the Luhn sum), IBAN, and national IDs such as SSN, NI number, Aadhaar (checked with Verhoeff) and PAN. A table's column headers add what no pattern can see: `person_name`, `address` and `date_of_birth`. `pii_columns` says which column each count came from. The report never repeats the data it found.

**Languages.** A BCP-47 tag per paragraph or message: `en-US`, `en-IN`, `hi` (Hindi in Devanagari), `hi-Latn` (Hindi in Roman script, as Hinglish is usually typed). Mixed-language text is called *code-switched*.

**Locale pack.** The rules for one language and market: phone and ID formats, currency, dates, privacy law notes, which recipes can speak the language. Chosen with `-l` (`en-US`, `en-GB`, `en-IN`, `hi-Latn-IN`) or taken from the project. Pick the one your data comes from: an Indian pack does not recognise a US phone number.

**Two-channel audio.** A stereo recording with the caller on one channel and the agent on the other, which is what a full-duplex model needs to adapt on.

**Narrowband.** Telephone-quality audio, sampled at 8 kHz or less, which recognition models handle worse than wideband.

## Deciding (`recommend`)

**Goal.** What you want to change about the assistant. There are seven:

| Goal | Means | Usual fix |
|---|---|---|
| knowledge | Know your prices, policies, FAQs | Retrieval, never a fine-tune |
| tools | Look things up, book, open tickets | Tools over your tables |
| workflow | Follow your call flow, tone and hand-offs | Behaviour fine-tune, after the baseline |
| recognition | Hear your callers' accents, names and amounts | Contextual biasing, then speech-to-text training |
| voice | Sound like a particular speaker | Voice cloning, with that speaker's consent |
| duplex | Handle interruptions naturally | A base model that is already full-duplex |
| language | Speak or understand another language | A locale pack and a model that speaks it |

**Primary problem.** The goal the data points to first. "none yet" means nothing in the folder is evidence for any goal.

**Route.** Where each kind of source goes: documents → retrieval, tables → tools, chats → behaviour fine-tune, audio → contextual biasing then recognition, two-channel audio → duplex model choice, non-English text → locale pack. With nothing usable, the route is *synth*.

**Retrieval.** Looking facts up at answer time instead of training them into the model, so prices and policies stay current.

**Behaviour fine-tune.** Training the model on real conversations so it learns how your team handles a call: the steps, the tone, when to hand off.

**Contextual biasing.** Steering speech recognition towards your product, place and customer names while it listens, which cuts errors on them without training.

**Bar.** How much data a goal needs before fine-tuning it is worth trying, in the goal's own unit (turns, hours or seconds). Each bar has a *floor* and usually a *target*.

**Floor.** Below it there is too little to learn from, so the verdict is *no* (`floor` in `recommend.json`).

**Target.** What the cited work used. Between the floor and the target, the verdict is *baseline first* (`need` in `recommend.json`).

**Verdict.** One of three answers per goal, never a bare yes (`eligibility` in `recommend.json`):

| Printed | In the JSON | Means |
|---|---|---|
| no | `blocked` | Fine-tuning is the wrong tool for this goal, or there is too little data |
| baseline first | `baseline_first` | Plausible, but measure the baseline first; it decides whether training is needed |
| worth trying | `candidate` | The data clears the bar; try it after the baseline, and compare |

The project-level *fine-tune?* line is the best verdict any goal reached.

**Baseline.** The base model measured with a good prompt, retrieval and tools on a held-out set of real conversations. It is what a fine-tune has to beat; without it, there is no proof training helped.

**Held-out set.** Real conversations kept out of training and used only to measure. Synthetic data can fill gaps in training, but the held-out set stays real.

**Evidence and confidence.** Every bar cites where its number comes from, labelled `measured` (a paper measured it), `reported` (a model team stated it) or `heuristic` (vakforge chose it, and nothing yet supports or refutes it).

**Not counted.** Material that exists but cannot count towards a bar yet, and what it needs first: hours of audio that have not been transcribed, for example.

**Blocked on.** What stands between a goal and training besides the amount of data: for example, a duplex recipe that needs the caller and the agent on separate channels when the recordings cannot show that. The GPU you need is shown on the recipe line instead.

**Recipe.** A researched path from an open base model to a trained assistant (`lfm25-audio`, `moshi-lora`, `qwen-omni`, `cascade`). None has been built yet; see [recipes](RECIPES.md).

**Method.** How a recipe plans to train (`recipe_method` in `recommend.json`). *LoRA* trains small added weights beside a frozen model; a *full fine-tune* updates every weight and needs more memory. The method is each upstream trainer's documented approach, marked *planned* because no recipe has run end to end yet. QLoRA (LoRA over a 4-bit model) is not suggested: nothing has verified it for these audio models.

**Synth.** Generating example conversations in your language to cover the cases your data does not. It buys coverage for a first version; it does not replace real data.

**Full-duplex.** A model that can listen while it speaks, so a caller can interrupt it. It comes from the base model, not from fine-tuning on a company's calls.

## Privacy (`prepare`, `validate`)

**Redaction.** Replacing personal data with a placeholder such as `<PHONE_1>` before any training row is written. The prepare step does it; [data format](DATA_FORMAT.md) describes the redaction log.

**Consent basis.** Why a recording may be used for training, recorded on every row. A recording with no consent basis is not a training row.

**Placeholder.** The token that replaces a piece of personal data, kept the same within a conversation so the dialogue still makes sense.
