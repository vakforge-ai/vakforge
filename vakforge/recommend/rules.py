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
        3,
        60,
        "measured",
        "VALL-E (arXiv 2301.02111) clones a voice from a 3-second prompt and YourTTS "
        "fine-tunes a speaker in under a minute; hours of audio are not the constraint here, "
        "consent for that speaker's voice is",
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

# recipe -> minimum GPU memory to train, and the goals it addresses
RECIPES: dict[str, dict[str, Any]] = {
    "lfm25-audio": {"gpu": 24, "goals": {"tools", "workflow", "recognition"}, "duplex": False},
    "moshi-lora": {"gpu": 48, "goals": {"duplex", "voice", "workflow"}, "duplex": True},
    "qwen-omni": {"gpu": 80, "goals": {"language", "tools", "workflow"}, "duplex": False},
    "cascade": {
        "gpu": 24,
        "goals": {"recognition", "language", "voice", "workflow"},
        "duplex": False,
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
    need: float | None
    unit: str
    evidence: str
    confidence: Confidence
    recipe: str | None
    recipe_support: str | None
    recipe_reason: str
    blockers: list[str]  # what stands between this goal and training, beyond data volume


@dataclass
class Recommendation:
    """What to change across the whole project, and the per-goal matrix it rests on.

    `fine_tune` is the project-level roll-up — the best state any goal reached — and is
    deliberately not a boolean. Read `goal_decisions` for the answer that applies to the
    thing you actually care about.
    """

    primary_problem: Goal
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


def infer_goals(summary: dict[str, Any], pack: LocalePack) -> list[Goal]:
    """What the data suggests the user wants, most likely first.

    Reads `profiled`, not `counts`: a file that was found but could not be read proves
    nothing about what the user wants to build.
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
    non_native = [lang for lang in summary.get("languages", {}) if not lang.startswith("en")]
    if non_native and any(v != "native" for v in pack.resolved("recipe_support").values()):
        goals.append("language")
    return goals or ["knowledge"]


def _routes(summary: dict[str, Any], goals: list[Goal]) -> list[Route]:
    counts = summary.get("counts", {})
    routes: list[Route] = []
    if counts.get("document", 0):
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
    if counts.get("audio", 0):
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
        routes.append(
            Route(
                "nothing yet", "synth", "generate scenario dialogues, ship a v0, collect real data"
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
        if gpu < spec["gpu"]:
            return (
                name,
                level,
                f"{name} fits, but training needs a {spec['gpu']} GB GPU "
                f"(you have {c.gpu}); use Colab or rent one",
                blockers,
            )
        note = (
            ""
            if level == "native"
            else f" ({level}: input understood, speech output stays English)"
        )
        return name, level, f"{name}: {primary} on a {spec['gpu']} GB GPU{note}", blockers
    return None, None, "no recipe fits: " + "; ".join(reasons), []


_UNIT_NAME = {
    "turns": "conversation turns",
    "hours": "hours of audio",
    "seconds": "seconds of audio",
}


def _amount(value: float, unit: str) -> str:
    return f"{value:g} {_UNIT_NAME[unit]}"


def _evidence(bar: Bar, summary: dict[str, Any]) -> tuple[float, str, list[str], bool]:
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
                f"{audio_hours:g} h of audio contributes no turns until it is transcribed "
                "and diarized; inspect does neither"
            )
        return float(messages), f"{messages} parsed chat messages", uncounted, True

    if bar.unit == "hours":
        return (
            audio_hours,
            f"{audio_hours:g} h of recordings",
            [
                "duration only: no transcripts, no speaker labels and no consent record, "
                "all of which recognition training needs"
            ],
            False,
        )

    seconds = audio_hours * 3600
    return (
        seconds,
        f"{seconds:g} s of recordings",
        [
            "not verified as one consented speaker recorded under consistent conditions, "
            "which is what a voice fine-tune actually needs"
        ],
        False,
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
            f"{primary}; generate coverage with synth, ship on retrieval and tools, and "
            "collect real conversations",
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
    have, have_from, uncounted, verified = _evidence(bar, summary)
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
        need=bar.target,
        unit=bar.unit,
        evidence=bar.evidence,
        confidence=bar.confidence,
        recipe=recipe,
        recipe_support=level,
        recipe_reason=recipe_reason,
        blockers=blockers,
    )


_RANK: dict[Eligibility, int] = {"blocked": 0, "baseline_first": 1, "candidate": 2}


def _project_verdict(decisions: list[GoalDecision]) -> tuple[Eligibility, str]:
    """Roll the matrix up: is any training worth attempting on this project at all?"""
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


def recommend(
    summary: dict[str, Any], pack: LocalePack, c: Constraints = DEFAULT_CONSTRAINTS
) -> Recommendation:
    """Apply the decision guide to an inspect summary."""
    goals = list(c.goals) or infer_goals(summary, pack)
    if c.duplex and "duplex" not in goals:
        goals.insert(0, "duplex")
    primary: Goal = "duplex" if c.duplex else goals[0]
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
                f"{d.goal}: {d.have:g} of ~{_amount(d.need, d.unit)} ({d.confidence}); "
                "run synth over your documents and tools for coverage, and keep the "
                "evaluation set real"
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
