import json
import re
from pathlib import Path

from vakforge.html_report import _cap, _n, _t, render

EXAMPLE = Path(__file__).parents[2] / "examples" / "hinglish-shop" / "expected"


def load(name: str) -> dict:
    return json.loads((EXAMPLE / name).read_text(encoding="utf-8"))


def test_the_example_renders_every_section():
    page = render(load("inspect.json"), load("recommend.json"))
    for heading in ("At a glance", "Recommendation", "Languages", "Personal data", "Files"):
        assert f"<h2>{heading}</h2>" in page
    assert "lookup_orders_by_order_id" in page
    assert "hi-Latn-IN" in page


def test_without_a_recommendation_the_page_has_no_recommendation():
    page = render(load("inspect.json"))
    assert "<h2>Recommendation</h2>" not in page
    assert "<h2>Files</h2>" in page


def test_the_page_fetches_nothing():
    # It has to open offline and travel as one file: no stylesheet, script or image URL.
    page = render(load("inspect.json"), load("recommend.json"))
    assert not re.search(r'(src|href)="(?!https://vakforge\.pages\.dev/docs/)[^"#]+"', page)
    assert "@import" not in page
    assert "url(http" not in page


def test_names_from_the_folder_are_escaped():
    # File and column names come from the user's folder, and the page is opened by others.
    report = load("inspect.json")
    report["files"][0]["path"] = "<script>alert(1)</script>.md"
    page = render(report)
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;.md" in page


def test_chat_speaker_names_stay_out_of_the_page():
    # In a WhatsApp export the speakers are people; the report counts them, never names them.
    report = load("inspect.json")
    chat = next(f for f in report["files"] if f["kind"] == "chat")
    speakers = list(chat["facts"]["speakers"])
    page = render(report)
    assert speakers
    assert not any(name in page for name in speakers)


def test_sentences_start_with_a_capital_but_names_keep_their_spelling():
    assert _cap("measure the base model") == "Measure the base model"
    assert _cap("non-English turns found") == "Non-English turns found"
    # Recipe names and locale tags are spelled the way they are, even first in a sentence.
    assert _cap("lfm25-audio fits, but") == "lfm25-audio fits, but"
    assert _cap("cascade fits, but") == "cascade fits, but"
    assert _cap("en-US: No single federal") == "en-US: No single federal"
    assert _cap("hi-Latn-IN: The Digital") == "hi-Latn-IN: The Digital"


def test_counts_in_prose_are_grouped_but_arxiv_ids_are_not():
    text = "2002646 turns clear the bar (arXiv 2305.11206)"
    assert _t(text) == "2\u202f002\u202f646 turns clear the bar (arXiv 2305.11206)"


def test_counts_are_grouped_the_same_way_in_every_locale():
    assert _n(2002646) == "2\u202f002\u202f646"
    assert _n(600) == "600"
    assert _n(0.5343) == "0.5343"


def test_a_report_from_0_2_0_without_floor_or_method_still_renders():
    rec = load("recommend.json")
    for goal in rec["goal_decisions"]:
        goal.pop("floor"), goal.pop("recipe_method")
    page = render(load("inspect.json"), rec)
    assert "Target ~" in page and "Minimum " not in page


def test_the_planned_method_is_labelled_as_planned():
    rec = load("recommend.json")
    rec["goal_decisions"][0]["recipe_method"] = "LoRA with the official kyutai-labs/moshi-finetune"
    page = render(load("inspect.json"), rec)
    assert '<span class="badge muted">Planned</span> LoRA with the official' in page


def test_the_page_names_the_folder_not_its_full_path():
    # An absolute path can carry a person's or a client's name into a shared page.
    report = load("inspect.json")
    report["root"] = "C:/Users/priya.sharma/clients/acme-bank/data"
    page = render(report)
    assert "<h1>data</h1>" in page
    assert "priya" not in page and "acme-bank" not in page


def test_no_personal_data_found_is_not_a_clean_bill():
    report = load("inspect.json")
    report["summary"]["pii"] = {}
    assert "does not show that the files hold no personal data" in render(report)
