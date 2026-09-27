"""Decision rules. Inputs: the `inspect.json` summary, the locale pack, user constraints.

Each goal carries its own bar, its own unit and the evidence behind it (docs/RESEARCH.md).
Where we chose a number ourselves it is marked `heuristic` and the CLI prints that, because
a made-up threshold presented as a requirement is the failure mode this module exists to
avoid. The verdict is never a plain yes: a goal is `blocked` (fine-tuning is the wrong tool
for it), `baseline_first` (plausible, but prompt, retrieval and biasing come first and
decide whether training is needed at all), or `candidate` (the data clears the bar, so it is
worth trying once the baseline is measured).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from vakforge.locales.base import LocalePack

Goal = Literal["knowledge", "tools", "workflow", "recognition", "voice", "duplex", "language"]
Gpu = Literal["none", "24", "48", "80"]
Eligibility = Literal["blocked", "baseline_first", "candidate"]
Confidence = Literal["measured", "reported", "heuristic"]

GOALS: tuple[Goal, ...] = (
    "knowledge",
    "tools",
    "workflow",
    "recognition",
    "voice",
    "duplex",
    "language",
)
GPU_GB = {"none": 0, "24": 24, "48": 48, "80": 80}
# How each verdict reads to a person, in the terminal and in the HTML report alike.
VERDICT_LABELS: dict[Eligibility, str] = {
    "blocked": "no",
    "baseline_first": "baseline first",
    "candidate": "worth trying",
}


@dataclass(frozen=True)
class Bar:
    """How much data a goal needs before fine-tuning it is worth attempting.

    `floor` is the point below which there is nothing to learn from; `target` is what the
    cited work used, or None where the literature gives no number. `confidence` says whether
    anyone measured this or we picked it.
    """

    unit: Literal["turns", "hours", "seconds"]
    floor: float
    target: float | None
    confidence: Confidence
    evidence: str


# Per goal: what fine-tuning it actually requires, and what the evidence says instead.
BARS: dict[Goal, Bar] = {
    "knowledge": Bar(
        "turns",
        0,
        None,
        "measured",
        "Ovadia et al. 2024 (arXiv 2312.05934): retrieval beat unsupervised fine-tuning for "
        "both existing and new facts. Gekhman et al. 2024 (arXiv 2405.05904): training on "
        "new-knowledge examples raises hallucination roughly linearly",
    ),
    "workflow": Bar(
        "turns",
        200,
        600,
        "heuristic",
        "LIMA (arXiv 2305.11206) got style and format from 1,000 curated examples and "
        "Spec-TOD (arXiv 2507.04841) was competitive on ~840 dialogues, but neither "
        "validates 600 or 200. Branch coverage and quality matter more than the count",
    ),
    "tools": Bar(
        "turns",
        200,
        8000,
        "reported",
        "Published tool-learning corpora run 8k to 60k examples (BUTTONInstruct 8k, "
        "APIGen 60k over 3,673 APIs, ToolACE across 26,507 APIs). Those are the sizes of "
        "broad general-purpose corpora, not a measured minimum for adapting one company's "
        "fixed set of tools, so treat 8k as the scale of the published work rather than a "
        "requirement: your tool count, argument branches and negative cases matter more. "
        "The schema and the prompt come first either way",
    ),
    "recognition": Bar(
        "hours",
        10,
        20,
        "measured",
        "20 h of Indian-accented speech took WER from 22.24% to 8.33% (arXiv 2409.11107). "
        "Contextual biasing cuts entity errors 18-50% with no training at all "
        "(arXiv 2506.06252, 2505.19179), so try that before collecting hours",
    ),
    "voice": Bar(
        "seconds",
        30,
        60,
        "heuristic",
        "Two different things get quoted together here, so this bar covers only one of "
        "them. VALL-E's 3 seconds (arXiv 2301.02111) is an inference-time prompt to a model "
        "already pretrained on 60k hours — it needs no training data from you at all, and if "
        "a zero-shot prompt is enough, the answer is not to fine-tune. YourTTS fine-tunes a "
        "speaker in under a minute, which is real adaptation evidence but for one model. "
        "The floor here is ours: no published work establishes a minimum for adapting an "
        "arbitrary voice model. What actually decides it is clean audio from one consented "
        "speaker under consistent conditions, not the total length",
    ),
    "duplex": Bar(
        "hours",
        1000,
        1200,
        "measured",
        "Full-duplex behaviour is a property of the base model, not something a company "
        "dataset teaches: PersonaPlex used ~1,217 h of real telephone audio plus 2,250+ h "
        "synthetic, and Moshi (arXiv 2410.00037) thousands of hours of stereo dialogue over "
        "a 7M-hour pretrained base. Pick a model that is already duplex, then adapt lightly",
    ),
    "language": Bar(
        "turns",
        200,
        None,
        "measured",
        "CS-YODAS moved Hindi-English accuracy from 0% to 19.9% with natural code-switched "
        "training where synthetic alone failed. Synthetic data buys coverage; natural "
        "code-switching and the evaluation set have to be real",
    ),
}

# recipe -> minimum GPU memory to train, the goals it addresses, and how it trains. The
# method is the plan in docs/RECIPES.md, from each upstream trainer's own documentation;
# no recipe has run end to end yet, and anything the upstream does not document says so.
RECIPES: dict[str, dict[str, Any]] = {
    "lfm25-audio": {
        "gpu": 24,
        "goals": {"tools", "workflow", "recognition"},
        "duplex": False,
        "method": "full fine-tune in bf16 with the upstream liquid_audio trainer; LoRA "
        "only if that trainer supports it, which is not verified",
    },
    "moshi-lora": {
        "gpu": 48,
        "goals": {"duplex", "voice", "workflow"},
        "duplex": True,
        "method": "LoRA with the official kyutai-labs/moshi-finetune",
    },
    "qwen-omni": {
        "gpu": 80,
        "goals": {"language", "tools", "workflow"},
        "duplex": False,
        "method": "LoRA on the Thinker with the Talker frozen, via ms-swift",
    },
    "cascade": {
        "gpu": 24,
        "goals": {"recognition", "language", "voice", "workflow"},
        "duplex": False,
        "method": "LoRA on a small instruct LLM (Unsloth or LLaMA-Factory); the "
        "speech-to-text model is fine-tuned on its own",
    },
}


@dataclass(frozen=True)
class Constraints:
    goals: tuple[Goal, ...] = ()  # empty: infer from the data
    gpu: Gpu = "none"
    duplex: bool = False  # sub-300 ms with interruptions required


@dataclass
class Route:
    source: str
    route: str
    why: str


@dataclass
class GoalDecision:
    """The answer for one goal, decided on that goal's own evidence.

    Every goal has its own unit, bar, verdict and recipe. Collapsing a project into one
    verdict hid the fact that "tools" and "recognition" are different questions with
    different data behind them and different answers.
    """

    goal: Goal
    eligibility: Eligibility
    reason: str
    have: float
    have_from: str  # what was counted to get `have`, in words
    uncounted: list[str]  # material that exists but cannot count yet, and what it needs
    floor: float  # below this there is nothing to learn from; 0 when volume is not the question
    need: float | None
    unit: str
    evidence: str
    confidence: Confidence
    recipe: str | None
    recipe_support: str | None
    recipe_reason: str
    recipe_method: str | None  # how the recipe plans to train: LoRA, full fine-tune, ...
    blockers: list[str]  # what stands between this goal and training, beyond data volume


@dataclass
class Recommendation:
    """What to change across the whole project, and the per-goal matrix it rests on.

    `fine_tune` is the project-level roll-up — the best state any goal reached — and is
    deliberately not a boolean. Read `goal_decisions` for the answer that applies to the
    thing you actually care about.
    """

    primary_problem: Goal | None  # None: nothing in the folder is evidence for any goal yet
    goals: list[Goal]
    routes: list[Route]
    goal_decisions: list[GoalDecision]
    fine_tune: Eligibility
    fine_tune_reason: str
    audio_hours: float
    consent: list[str]
    next_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def decision(self, goal: Goal) -> GoalDecision | None:
        """The decision for one goal, or None if it was not among the goals."""
        return next((d for d in self.goal_decisions if d.goal == goal), None)


def _non_english_share(summary: dict[str, Any]) -> float:
    """The share of sampled paragraphs and messages that are not English.

    The language goal exists because the recipes' base models are English, so English is
    the line it draws, whatever the locale.
    """
    langs = summary.get("languages", {})
    sampled = sum(langs.values())
    other = sum(n for lang, n in langs.items() if not lang.startswith("en"))
    return other / sampled if sampled else 0.0


def infer_goals(summary: dict[str, Any], pack: LocalePack) -> list[Goal]:
    """What the data suggests the user wants, most likely first.

    Reads `profiled`, not `counts`: a file that was found but could not be read proves
    nothing about what the user wants to build.

    An empty list means nothing here is evidence for any goal. It used to fall back to
    "knowledge", which then explained that "facts belong in retrieval" about a folder with
    no documents in it.
    """
    goals: list[Goal] = []
    profiled = summary.get("profiled") or summary.get("counts", {})
    if summary.get("tool_candidates"):
        goals.append("tools")
    if summary.get("chat_messages", 0) or profiled.get("audio", 0):
        goals.append("workflow")
    if profiled.get("audio", 0):
        goals.append("recognition")
    if profiled.get("document", 0) or summary.get("document_words", 0):
        goals.append("knowledge")
    if _non_english_share(summary) and any(
        v != "native" for v in pack.resolved("recipe_support").values()
    ):
        goals.append("language")
    return goals


def _routes(summary: dict[str, Any], goals: list[Goal]) -> list[Route]:
    counts = summary.get("counts", {})
    # Routes follow what was read, as goals do: two unreadable PDFs used to get "documents
    # -> retrieval" beside a verdict that nothing in the folder was usable.
    profiled = summary.get("profiled") or counts
    labelled = summary.get("labelled_text_tables", 0)
    routes: list[Route] = []
    if profiled.get("document", 0):
        routes.append(
            Route(
                "documents",
                "retrieval",
                "facts change; keep them out of weights and look them up at answer time",
            )
        )
    if summary.get("tool_candidates"):
        cands = ", ".join(summary["tool_candidates"][:4])
        routes.append(Route("tables", "tools", f"expose lookups as tools: {cands}"))
    if summary.get("chat_messages", 0):
        routes.append(
            Route(
                "chats",
                "behaviour fine-tune",
                "real conversations teach flow, tone and hand-offs; "
                "measure the prompt-only baseline first",
            )
        )
    if profiled.get("audio", 0):
        routes.append(
            Route(
                "audio",
                "contextual biasing, then recognition",
                "transcribe, diarize and redact first; then bias the recogniser towards your "
                "product and customer names, which cuts entity errors without training, and "
                "only collect accent hours if that still misses",
            )
        )
        if summary.get("two_channel_audio_files", 0):
            routes.append(
                Route(
                    "two-channel audio",
                    "duplex model choice",
                    "separate user and agent channels are what a full-duplex model needs to "
                    "adapt on, but duplex behaviour comes from picking an already-duplex base "
                    "model, not from these hours",
                )
            )
    if "language" in goals:
        routes.append(
            Route(
                "languages",
                "locale pack",
                "non-English turns found; the pack decides which recipe can speak the language",
            )
        )
    if not routes:
        start = "generate scenario dialogues, ship a v0, collect real data"
        found = fmt_kinds(counts)
        if found:
            # Say what was there and why it did not count, so a folder of unusable files
            # does not read as empty, and an unread file is not blamed on its columns.
            why = []
            unread = sum(counts.values()) - sum(profiled.values())
            if unread:
                why.append(
                    f"{unread} file{'s' if unread > 1 else ''} could not be read (the inspect "
                    "report says why)"
                )
            if profiled.get("table", 0) > labelled:
                why.append("a table needs an id column to look records up by")
            if labelled:
                why.append("vakforge does not use tables of labelled texts yet")
            routes.append(
                Route(
                    "nothing usable yet",
                    "synth",
                    f"found {found}, but none of it is evidence for a goal: "
                    f"{'; '.join(why) or 'nothing in it answers a goal'}. Meanwhile, {start}",
                )
            )
        else:
            routes.append(Route("nothing yet", "synth", start))
    if labelled:
        routes.append(
            Route(
                "labelled texts",
                "not used yet",
                "a text column with a category beside it, such as an intent dataset, is "
                "neither a conversation nor a lookup table, and vakforge does not read it yet; "
                "real requests like these still make good test questions for the baseline",
            )
        )
    return routes


def _pick_recipe(
    primary: Goal, c: Constraints, pack: LocalePack, stereo: bool
) -> tuple[str | None, str | None, str, list[str]]:
    support = pack.resolved("recipe_support") or {}
    gpu = GPU_GB[c.gpu]
    wants_duplex = c.duplex or primary == "duplex"
    order = (
        ["moshi-lora", "lfm25-audio", "qwen-omni", "cascade"]
        if wants_duplex
        else [
            "lfm25-audio",
            "cascade",
            "qwen-omni",
            "moshi-lora",
        ]
    )
    reasons = []
    for name in order:
        spec = RECIPES[name]
        level = support.get(name, "unsupported")
        if level == "unsupported":
            reasons.append(f"{name}: locale marks it unsupported")
            continue
        if wants_duplex and not spec["duplex"]:
            reasons.append(f"{name}: not full-duplex")
            continue
        if primary not in spec["goals"] and not wants_duplex:
            reasons.append(f"{name}: does not target {primary}")
            continue
        # Missing dual-stream data blocks *adapting* this model. It does not stop us
        # naming it: choosing a base that can already hold a duplex conversation is a
        # separate decision from whether your recordings can adapt it.
        blockers = []
        if name == "moshi-lora" and not stereo:
            blockers.append(
                "adapting it needs recordings with the user and the agent on separate "
                "channels; inspect can see two channels but cannot verify who is on each"
            )
        note = {
            "understand_only": " (understand_only: input understood, speech output stays English)",
            "cascade": " (cascade: runs through the locale pack's speech-to-text and TTS)",
        }.get(level, "")
        if gpu < spec["gpu"]:
            return (
                name,
                level,
                f"{name} fits{note}, but training needs a {spec['gpu']} GB GPU "
                f"(you have {c.gpu}); use Colab or rent one",
                blockers,
            )
        return name, level, f"{name}: {primary} on a {spec['gpu']} GB GPU{note}", blockers
    return None, None, "no recipe fits: " + "; ".join(reasons), []


_UNIT_NAME = {
    "turns": "conversation turns",
    "hours": "hours of audio",
    "seconds": "seconds of audio",
}


def fmt_number(value: float) -> str:
    """A count as people write it. `:g` prints 2002646 as 2.00265e+06 past six digits,
    which is how a million-message export was reported."""
    return f"{value:.15g}"


def fmt_kinds(counts: dict[str, int]) -> str:
    """File counts in words: "1 document, 2 tables, 3 audio". Shared by inspect and
    recommend, so neither writes "2 document" again."""
    return ", ".join(
        f"{n} {kind}{'s' if n > 1 and kind not in {'audio', 'other'} else ''}"
        for kind, n in counts.items()
        if n
    )


def _amount(value: float, unit: str) -> str:
    return f"{fmt_number(value)} {_UNIT_NAME[unit]}"


def _language_evidence(
    summary: dict[str, Any], messages: int, uncounted: list[str]
) -> tuple[float, str, list[str], bool]:
    """Chat messages actually checked and found not to be English.

    Only counted turns are evidence. An estimate from the first messages of each file (the
    share of sampled text that is not English, times every message) turned 200 Hinglish
    messages followed by 1,000 English ones into 1,200 turns, and mixed document
    paragraphs in with chat messages.
    """
    checked = summary.get("chat_languages")
    if checked is None:
        # A report from vakforge 0.3.0 or earlier has no per-message counts: estimate, and
        # keep the verdict short of `candidate` until inspect has counted them.
        share = _non_english_share(summary)
        turns = round(messages * share)
        return (
            float(turns),
            f"~{turns} of {messages} parsed chat messages, estimated from the first "
            "messages and paragraphs of each file",
            [
                "an estimate, not a count: run inspect again with vakforge 0.3.1 or later "
                "to check the language of every chat message",
                *uncounted,
            ],
            False,
        )
    seen = sum(n for lang, n in checked.items() if not lang.startswith("en"))
    total = sum(checked.values())
    have_from = f"{seen} of the {total} chat messages checked are not in English"
    if total < messages:
        have_from += f"; {messages - total} more were counted but not read"
    return float(seen), have_from, uncounted, True


def _evidence(goal: Goal, bar: Bar, summary: dict[str, Any]) -> tuple[float, str, list[str], bool]:
    """What the data can actually prove for this bar: (amount, counted, uncounted, verified).

    Raw audio is never converted into conversation turns. An hour of recording is not 300
    turns until something has transcribed and diarized it, and `inspect` does neither: it
    reads duration, sample rate and channel count. Counting it as turns produced a
    `candidate` verdict from material that cannot train anything yet, which is the single
    most misleading thing this module used to do.

    `verified` is False when the amount is real but its fitness is unproven, which stops
    the verdict short of `candidate`.
    """
    audio_hours = float(summary.get("audio_hours", 0.0))
    messages = int(summary.get("chat_messages", 0))

    if bar.unit == "turns":
        uncounted = []
        if audio_hours:
            uncounted.append(
                f"{fmt_number(audio_hours)} h of audio contributes no turns until it is "
                "transcribed and diarized; inspect does neither"
            )
        if goal == "language":
            return _language_evidence(summary, messages, uncounted)
        if goal == "tools":
            # A conversation is not a tool-call example, and 8,000 of them with no tool in
            # sight used to make tool training "worth trying".
            note = (
                "conversations are not tool-call examples: nothing in them marks which turn "
                "calls a tool, with what arguments and what came back"
            )
            if not summary.get("tool_candidates"):
                note += ", and no table here offers a lookup to call"
            return float(messages), f"{messages} parsed chat messages", [note, *uncounted], False
        return float(messages), f"{messages} parsed chat messages", uncounted, True

    if bar.unit == "hours":
        return (
            audio_hours,
            f"{fmt_number(audio_hours)} h of recordings",
            [
                "duration only: no transcripts, no speaker labels and no consent record, "
                "all of which recognition training needs"
            ],
            False,
        )

    seconds = audio_hours * 3600
    return (
        seconds,
        f"{fmt_number(seconds)} s of recordings",
        [
            "not verified as one consented speaker recorded under consistent conditions, "
            "which is what a voice fine-tune actually needs"
        ],
        False,
    )


# What to do when a goal is short of data, in terms of that goal. It was one sentence for
# every goal, "generate coverage with synth", which is the opposite of the evidence for
# recognition (biasing first, then real accented speech) and for language (synthetic
# code-switching alone did not move accuracy).
_SHORTFALL: dict[Goal, str] = {
    "recognition": (
        "try contextual biasing towards your names first; if it still misses, collect real "
        "recordings of your callers, transcribed and with consent"
    ),
    "voice": (
        "try a zero-shot voice prompt first; a fine-tune needs clean audio of one speaker "
        "who consented to their voice being used"
    ),
    "language": (
        "collect real code-switched conversations; synth adds coverage but alone did not "
        "move accuracy, and the evaluation set has to be real"
    ),
}


def _short_of(goal: Goal, step: bool = False) -> str:
    """The shortfall advice for `goal`: in the verdict's reason, or as a next step."""
    if goal in _SHORTFALL:
        return _SHORTFALL[goal]
    if step:
        return (
            "run synth over your documents and tools for coverage, and keep the evaluation set real"
        )
    return (
        "generate coverage with synth, ship on retrieval and tools, and collect real conversations"
    )


def _verdict(primary: Goal, bar: Bar, have: float) -> tuple[Eligibility, str]:
    """Which of the three states this goal is in, and why, in the user's own numbers."""
    if primary == "knowledge":
        return (
            "blocked",
            "facts belong in retrieval, not in weights: fine-tuning on them goes stale and "
            "measurably raises hallucination, while retrieval answers the same questions today",
        )
    if primary == "duplex":
        return (
            "blocked",
            "you cannot fine-tune your way to full duplex: start from a base model that "
            "already interrupts and barges in, then adapt its persona on your calls",
        )
    if have < bar.floor:
        return (
            "blocked",
            f"{_amount(have, bar.unit)} is below the {_amount(bar.floor, bar.unit)} floor for "
            f"{primary}; {_short_of(primary)}",
        )
    if bar.target is not None and have < bar.target:
        return (
            "baseline_first",
            f"{_amount(have, bar.unit)} against a {_amount(bar.target, bar.unit)} target "
            f"({bar.confidence}); measure prompt, retrieval and biasing first, because that "
            "baseline is what decides whether the gap is worth training on at all",
        )
    return (
        "candidate",
        f"{_amount(have, bar.unit)} clears the bar for {primary}; measure the prompt and "
        "retrieval baseline, then fine-tune only the part it fails and compare the two",
    )


def _decide(goal: Goal, summary: dict[str, Any], pack: LocalePack, c: Constraints) -> GoalDecision:
    """Answer one goal on its own evidence, bar and recipe."""
    bar = BARS[goal]
    have, have_from, uncounted, verified = _evidence(goal, bar, summary)
    eligibility, reason = _verdict(goal, bar, have)

    two_channel = bool(summary.get("two_channel_audio_files", 0))
    if eligibility == "blocked" and goal != "duplex":
        # Nothing to train on, so no recipe to name. Duplex is the exception: the verdict
        # is about training, but the user still has to pick a base model that can do it.
        recipe, level, recipe_reason, blockers = (
            None,
            None,
            "no recipe needed: retrieval and tools carry this one",
            [],
        )
    else:
        recipe, level, recipe_reason, blockers = _pick_recipe(goal, c, pack, two_channel)

    if eligibility == "candidate" and not verified:
        eligibility = "baseline_first"
        reason = (
            f"{_amount(have, bar.unit)} clears the bar for {goal}, but nothing has "
            f"verified it is usable — {uncounted[0]}. Measure the baseline while you "
            "establish that, and revisit"
        )
    elif eligibility == "candidate" and blockers:
        eligibility = "baseline_first"
        reason = f"the data clears the bar, but {blockers[0]}"

    return GoalDecision(
        goal=goal,
        eligibility=eligibility,
        reason=reason,
        have=round(have, 2),
        have_from=have_from,
        uncounted=uncounted,
        floor=bar.floor,
        need=bar.target,
        unit=bar.unit,
        evidence=bar.evidence,
        confidence=bar.confidence,
        recipe=recipe,
        recipe_support=level,
        recipe_reason=recipe_reason,
        recipe_method=RECIPES[recipe]["method"] if recipe else None,
        blockers=blockers,
    )


_RANK: dict[Eligibility, int] = {"blocked": 0, "baseline_first": 1, "candidate": 2}


def _project_verdict(decisions: list[GoalDecision]) -> tuple[Eligibility, str]:
    """Roll the matrix up: is any training worth attempting on this project at all?"""
    if not decisions:
        return "blocked", (
            "nothing here is evidence for any goal yet, so there is nothing to train. Add "
            "documents, a table with an id column, conversations or call audio, and run "
            "recommend again"
        )
    best = max(_RANK[d.eligibility] for d in decisions)
    named = {
        state: [d.goal for d in decisions if d.eligibility == state]
        for state in ("candidate", "baseline_first", "blocked")
    }
    if best == 2:
        return "candidate", (
            f"worth trying for {', '.join(named['candidate'])}, once the baseline is "
            "measured. Every other goal below has its own answer"
        )
    if best == 1:
        return "baseline_first", (
            f"nothing is ready to train yet. {', '.join(named['baseline_first'])} could be, "
            "once the baseline is measured and the gaps below are closed"
        )
    return "blocked", (
        "no goal here is one that fine-tuning answers, or has enough usable data to try. "
        "Ship on retrieval and tools, and collect real conversations"
    )


DEFAULT_CONSTRAINTS = Constraints()


class InspectSummary(BaseModel):
    """The part of `inspect.json` that `recommend` reads, checked before it is trusted.

    A report is a file, and a file can be hand-edited or arrive from somewhere else.
    Checking only that `summary` is an object would still let `{"counts": 5}` through to
    crash three functions later, so every field the rules read is typed here, once, at
    the entry point every caller goes through. Unknown keys are kept.
    """

    model_config = ConfigDict(extra="allow")

    counts: dict[str, int] = Field(default_factory=dict)
    profiled: dict[str, int] | None = None
    document_words: int = 0
    chat_messages: int = 0
    audio_hours: float = 0.0
    two_channel_audio_files: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    pii: dict[str, int] = Field(default_factory=dict)
    tool_candidates: list[str] = Field(default_factory=list)
    labelled_text_tables: int = 0
    chat_languages: dict[str, int] | None = None  # None: a report from 0.3.0 or earlier


def recommend(
    summary: dict[str, Any], pack: LocalePack, c: Constraints = DEFAULT_CONSTRAINTS
) -> Recommendation:
    """Apply the decision guide to an inspect summary.

    Raises `pydantic.ValidationError` if the summary does not have the shape `inspect`
    writes.
    """
    summary = InspectSummary.model_validate(summary).model_dump()
    goals = list(c.goals) or infer_goals(summary, pack)
    if c.duplex and "duplex" not in goals:
        goals.insert(0, "duplex")
    primary: Goal | None = "duplex" if c.duplex else (goals[0] if goals else None)
    routes = _routes(summary, goals)
    audio_hours = float(summary.get("audio_hours", 0.0))

    # Every goal is answered on its own evidence; the project verdict is the roll-up.
    decisions = [_decide(goal, summary, pack, c) for goal in goals]
    verdict, reason = _project_verdict(decisions)

    consent: list[str] = []
    if summary.get("counts", {}).get("audio", 0):
        rule = pack.resolved("call_recording_consent")
        consent.append(
            f"call recordings: consent rule for {pack.id} is '{rule}'; "
            "record a consent basis before prepare"
        )
    if summary.get("pii"):
        kinds = ", ".join(summary["pii"])
        consent.append(
            f"personal data found ({kinds}): prepare must redact text and audio "
            "before any training row is written"
        )
    notes = pack.resolved("privacy_notes")
    if notes:
        consent.append(f"{pack.id}: {notes.summary}")

    steps = [
        "measure the base model with prompt + retrieval on a held-out set of real "
        "conversations before training anything; that baseline is the only proof training "
        "was needed"
    ]
    if summary.get("tool_candidates"):
        steps.append("define the suggested tools and test the base model's tool calls")
    if any(d.goal == "recognition" for d in decisions):
        steps.append(
            "bias the recogniser towards your product, place and customer names; published "
            "results cut entity errors 18-50% with no training"
        )
    # One line per goal that still needs something, so a multi-goal project gets a
    # multi-goal plan instead of one instruction aimed at whichever goal sorted first.
    for d in decisions:
        if d.need is not None and d.have < d.need:
            steps.append(
                f"{d.goal}: {fmt_number(d.have)} of ~{_amount(d.need, d.unit)} ({d.confidence}); "
                f"{_short_of(d.goal, step=True)}"
            )
        for note in d.uncounted:
            steps.append(f"{d.goal}, not counted yet: {note}")
        for blocker in d.blockers:
            steps.append(f"{d.goal}, blocked on: {blocker}")
    trainable = [d for d in decisions if d.eligibility == "candidate" and d.recipe]
    if trainable:
        for d in trainable:
            steps.append(f"{d.goal}: fine-tune with {d.recipe} and compare base vs tuned")
    else:
        steps.append("ship the retrieval + tools version and collect real conversations")
    if not goals:
        # With no evidence there is no baseline to measure and nothing to ship yet.
        steps = [
            "nothing here is evidence yet: add documents, a table with an id column, "
            "conversations or call audio, then run recommend again",
            "or start without data: generate scenario dialogues with synth, ship a v0 and "
            "collect real conversations",
        ]

    return Recommendation(
        primary_problem=primary,
        goals=goals,
        routes=routes,
        goal_decisions=decisions,
        fine_tune=verdict,
        fine_tune_reason=reason,
        audio_hours=audio_hours,
        consent=consent,
        next_steps=steps,
    )
