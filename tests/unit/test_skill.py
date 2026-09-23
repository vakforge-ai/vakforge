"""The agent skill must stay loadable and self-consistent."""

import re
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parents[2] / "skill" / "vakforge"


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(m.group(1))


def test_frontmatter_has_name_and_trigger_description():
    fm = _frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    assert fm["name"] == "vakforge"
    for trigger in ("voice", "fine-tune", "retrieval", "Realtime", "Hinglish", "vakforge"):
        assert trigger in fm["description"], trigger


def test_every_referenced_file_exists():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    refs = set(re.findall(r"references/([\w-]+\.md)", text))
    assert refs, "SKILL.md should point at its references"
    for ref in refs:
        assert (SKILL / "references" / ref).exists(), ref
    on_disk = {p.name for p in (SKILL / "references").glob("*.md")}
    assert on_disk == refs, on_disk ^ refs


def test_cli_commands_named_in_skill_exist():
    from typer.main import get_command

    from vakforge.cli import app

    names = set(get_command(app).commands)
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for cmd in set(
        re.findall(r"vakforge (init|inspect|recommend|validate|locales|schema)\b", text)
    ):
        assert cmd in names, cmd


def test_every_recommendation_field_the_skill_names_exists():
    """The skill tells an agent which fields to read; drift makes it hallucinate them.

    Checking filenames and command names was not enough: `evidence_confidence` was renamed
    to `confidence` and the skill kept naming the old one, because nothing compared the two.
    """
    from vakforge.locales import get_pack
    from vakforge.recommend import recommend

    rec = recommend(
        {
            "counts": {"chat": 1, "audio": 1},
            "profiled": {"chat": 1, "audio": 1},
            "chat_messages": 400,
            "audio_hours": 2.0,
            "document_words": 0,
            "two_channel_audio_files": 0,
            "languages": {},
            "pii": {},
            "tool_candidates": ["lookup_orders_by_order_id"],
        },
        get_pack("en-US"),
    )
    from vakforge.recommend.rules import GOALS

    report = rec.to_dict()
    # Field names, plus the values the skill is entitled to name: eligibility states,
    # confidence labels and goals all appear in prose as `backticked` terms.
    available = (
        set(report)
        | set(report["goal_decisions"][0])
        | {"blocked", "baseline_first", "candidate"}
        | {"measured", "reported", "heuristic"}
        | set(GOALS)
    )

    # Only the Recommend step, because that is the section that names report fields;
    # elsewhere a backticked snake_case word is a package or a path.
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    step = re.search(r"^### 3\. Recommend$(.*?)^### 4\.", text, re.S | re.M)
    assert step, "SKILL.md no longer has a '### 3. Recommend' step"

    named = {w for w in re.findall(r"`([a-z][a-z_]*[a-z])`", step.group(1)) if "_" in w}
    known_not_fields = {"recommend_json", "inspect_json"}
    for field in named - known_not_fields:
        assert field in available, (
            f"SKILL.md tells the agent to read {field!r}, which recommend() does not produce. "
            f"Available: {sorted(available)}"
        )
