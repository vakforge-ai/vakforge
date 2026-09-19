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
