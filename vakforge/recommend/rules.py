"""Decision rules. Inputs: the `inspect.json` summary, the locale pack, user constraints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from vakforge.locales.base import LocalePack

Goal = Literal["knowledge", "tools", "workflow", "recognition", "voice", "duplex", "language"]
Gpu = Literal["none", "24", "48", "80"]

GOALS: tuple[Goal, ...] = (
    "knowledge",
    "tools",
    "workflow",
    "recognition",
    "voice",
    "duplex",
    "language",
)
TURNS_FOR_BEHAVIOUR = 600  # a few hundred to a few thousand turns covering every branch
TURNS_PER_AUDIO_HOUR = 300  # rough: a support call has ~5 turns a minute
HOURS_FOR_VOICE = 10  # voice, style and duplex want tens of hours of real conversation
GPU_GB = {"none": 0, "24": 24, "48": 48, "80": 80}

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
class Recommendation:
    primary_problem: Goal
    goals: list[Goal]
    routes: list[Route]
    fine_tune: bool
    fine_tune_reason: str
    recipe: str | None
    recipe_support: str | None
    recipe_reason: str
    turns_have: int
    turns_need: int
    audio_hours: float
    consent: list[str]
    next_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_goals(summary: dict[str, Any], pack: LocalePack) -> list[Goal]:
    """What the data suggests the user wants, most likely first."""
    goals: list[Goal] = []
    counts = summary.get("counts", {})
    if summary.get("tool_candidates"):
        goals.append("tools")
    if summary.get("chat_messages", 0) or counts.get("audio", 0):
        goals.append("workflow")
    if counts.get("audio", 0):
        goals.append("recognition")
    if counts.get("document", 0) or summary.get("document_words", 0):
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
        why = "transcribe, diarize, redact; then accents and timing from real calls"
        if summary.get("stereo_audio_files", 0):
            why += "; stereo files allow a full-duplex recipe"
        routes.append(Route("audio", "recognition and voice", why))
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
) -> tuple[str | None, str | None, str]:
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
        if name == "moshi-lora" and not stereo:
            reasons.append(f"{name}: needs stereo (user/agent) recordings")
            continue
        if primary not in spec["goals"] and not wants_duplex:
            reasons.append(f"{name}: does not target {primary}")
            continue
        if gpu < spec["gpu"]:
            return (
                name,
                level,
                f"{name} fits, but training needs a {spec['gpu']} GB GPU "
                f"(you have {c.gpu}); use Colab or rent one",
            )
        note = (
            ""
            if level == "native"
            else f" ({level}: input understood, speech output stays English)"
        )
        return name, level, f"{name}: {primary} on a {spec['gpu']} GB GPU{note}"
    return None, None, "no recipe fits: " + "; ".join(reasons)


DEFAULT_CONSTRAINTS = Constraints()


def recommend(
    summary: dict[str, Any], pack: LocalePack, c: Constraints = DEFAULT_CONSTRAINTS
) -> Recommendation:
    """Apply the decision guide to an inspect summary."""
    goals = list(c.goals) or infer_goals(summary, pack)
    primary: Goal = "duplex" if c.duplex else goals[0]
    routes = _routes(summary, goals)

    audio_hours = float(summary.get("audio_hours", 0.0))
    turns_have = int(summary.get("chat_messages", 0)) + int(audio_hours * TURNS_PER_AUDIO_HOUR)
    behavioural = {"tools", "workflow", "recognition", "voice", "duplex", "language"}
    needs_training = bool(behavioural & set(goals))
    turns_need = TURNS_FOR_BEHAVIOUR if needs_training else 0

    if not needs_training:
        fine_tune, reason = (
            False,
            "only documents: retrieval answers factual questions; "
            "fine-tuning would bake in facts that go stale",
        )
    elif turns_have == 0:
        fine_tune, reason = (
            False,
            "no conversations to learn from yet: start with retrieval and tools, "
            "generate dialogues with synth, collect real ones",
        )
    elif primary in {"voice", "duplex"} and audio_hours < HOURS_FOR_VOICE:
        fine_tune, reason = (
            False,
            f"{primary} needs about {HOURS_FOR_VOICE}+ hours of real calls; "
            f"you have {audio_hours:g}",
        )
    else:
        fine_tune, reason = (
            True,
            "conversations available; still measure the prompt + retrieval baseline first "
            "and fine-tune only what it fails",
        )

    stereo = bool(summary.get("stereo_audio_files", 0))
    recipe, level, recipe_reason = (
        _pick_recipe(primary, c, pack, stereo)
        if needs_training
        else (None, None, "no recipe needed for retrieval")
    )

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
        "measure the base model with prompt + retrieval on a held-out set before training anything"
    ]
    if summary.get("tool_candidates"):
        steps.append("define the suggested tools and test the base model's tool calls")
    if needs_training and turns_have < turns_need:
        steps.append(
            f"data gap: {turns_have} of ~{turns_need} turns; "
            "run synth over your documents and tools"
        )
    if fine_tune and recipe:
        steps.append(f"then fine-tune with {recipe} and compare base vs tuned with eval")
    if not fine_tune:
        steps.append("ship the retrieval + tools version and collect real conversations")

    return Recommendation(
        primary_problem=primary,
        goals=goals,
        routes=routes,
        fine_tune=fine_tune,
        fine_tune_reason=reason,
        recipe=recipe,
        recipe_support=level,
        recipe_reason=recipe_reason,
        turns_have=turns_have,
        turns_need=turns_need,
        audio_hours=audio_hours,
        consent=consent,
        next_steps=steps,
    )
