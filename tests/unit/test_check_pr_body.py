import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_pr_body", ROOT / "scripts/check_pr_body.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

TEMPLATE = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")


def filled(template: str = TEMPLATE) -> str:
    """The template with a line of real text under each prose section."""
    for section in check.PROSE:
        template = template.replace(f"## {section}\n", f"## {section}\n\nText for {section}.\n")
    return template


def test_the_template_filled_in_passes():
    assert check.problems(filled()) == []


def test_the_blank_template_fails_on_every_prose_section():
    # The template's <!-- hints --> are what a contributor sees before writing anything.
    found = check.problems(TEMPLATE)
    assert len(found) == 3
    assert all("is empty" in p for p in found)


def test_missing_sections_are_all_named_at_once():
    found = check.problems("## What\n\nA change.\n")
    assert found == [
        "missing the `## Why` section",
        "missing the `## How to check` section",
        "missing the `## Checklist` section",
    ]


def test_sections_out_of_order_are_reported():
    body = filled().replace("## What", "## Tmp").replace("## Why", "## What")
    body = body.replace("## Tmp", "## Why")
    assert any("out of order" in p for p in check.problems(body))


def test_a_checklist_without_its_task_list_fails():
    body = filled().split("## Checklist")[0] + "## Checklist\n\nAll done.\n"
    assert check.problems(body) == ["`## Checklist` has no `- [ ]` items; keep the template's list"]


def test_headings_match_whatever_their_case_and_line_endings():
    body = filled().replace("## What", "## what").replace("\n", "\r\n")
    assert check.problems(body) == []


def test_bots_are_not_checked_and_people_are(monkeypatch, capsys):
    monkeypatch.setenv("PR_BODY", "Bumps actions/checkout from 6 to 7.")
    monkeypatch.setenv("PR_AUTHOR", "dependabot[bot]")
    assert check.main() == 0
    monkeypatch.setenv("PR_AUTHOR", "someone")
    assert check.main() == 1
    assert "::error title=Pull request description::" in capsys.readouterr().out
