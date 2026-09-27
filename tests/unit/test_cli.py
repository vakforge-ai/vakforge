import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vakforge import __version__
from vakforge.cli import app
from vakforge.config import ProjectConfig

runner = CliRunner()


def flat(result) -> str:
    """CLI output with newlines and runs of spaces collapsed.

    Rich wraps to the console width, so a phrase can be split across lines when a long
    path pushes it past the margin, which happens on CI's `/tmp/pytest-of-runner/...`
    paths and not on a short Windows temp dir. Assert against this, not `result.output`.
    """
    return " ".join(result.output.split())


def test_version():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert __version__ in r.stdout


def test_init_creates_project(tmp_path):
    target = tmp_path / "my-assistant"
    r = runner.invoke(app, ["init", str(target), "--locale", "en-US", "--locale", "en-IN"])
    assert r.exit_code == 0, r.output
    assert (target / "data" / "raw").is_dir()
    assert (target / ".gitignore").read_text().startswith("# written by")
    assert ProjectConfig.load(target).locales == ["en-US", "en-IN"]


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_init_keeps_every_data_file_out_of_git(tmp_path):
    # Only data/raw/ and three audio extensions used to be ignored, so recordings in
    # data/audio/, prepared manifests and redaction logs could be committed.
    target = tmp_path / "shop"
    assert runner.invoke(app, ["init", str(target), "--locale", "en-US"]).exit_code == 0
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    private = [
        "data/raw/crm.csv",
        "data/audio/call.opus",
        "data/prepared/vakforge.jsonl",
        "data/prepared/redactions/conv_1.json",
        "runs/eval/report.json",
        "exports/call.m4a",
        # The reports, when written beside the project file rather than in runs/.
        "inspect.json",
        "recommend.json",
        "report.html",
    ]
    kept = ["vakforge.yaml", "configs/train.yaml"]
    check = ["git", "check-ignore", *private, *kept]
    ignored = subprocess.run(check, cwd=target, capture_output=True, text=True).stdout.split()
    assert ignored == private


def test_a_project_created_by_0_1_0_still_loads(tmp_path):
    # 0.1.0's init wrote data_dir into every vakforge.yaml; 0.2.0 must not reject it.
    (tmp_path / "vakforge.yaml").write_text(
        "name: shop\nlocales:\n- hi-Latn-IN\ndata_dir: data\n", encoding="utf-8"
    )
    assert ProjectConfig.load(tmp_path).locales == ["hi-Latn-IN"]
    (tmp_path / "data").mkdir()
    r = runner.invoke(app, ["inspect", str(tmp_path / "data"), "-o", str(tmp_path / "i.json")])
    assert r.exit_code == 0, r.output


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("name: shop\nlocales: [en-US]\ncolour: red\n", "colour"),
        ("name: shop\nlocales: []\n", "locales"),
        ("name: shop\nlocales: [en-US\n", "not a valid project file"),
        ("- just\n- a list\n", "not a valid project file"),
    ],
)
def test_a_bad_project_file_is_an_error_message_not_a_traceback(tmp_path, body, needle):
    (tmp_path / "vakforge.yaml").write_text(body, encoding="utf-8")
    (tmp_path / "data").mkdir()
    r = runner.invoke(app, ["inspect", str(tmp_path / "data"), "-o", str(tmp_path / "i.json")])
    assert r.exit_code == 2, r.output
    assert "not a valid project file" in flat(r) and needle in flat(r)
    assert "Traceback" not in r.output


def test_init_rejects_unknown_locale(tmp_path):
    r = runner.invoke(app, ["init", str(tmp_path / "x"), "--locale", "xx-YY"])
    assert r.exit_code == 2
    assert "unknown locale" in flat(r)


def test_validate_exit_codes(project):
    r = runner.invoke(app, ["validate", str(project / "vakforge.jsonl")])
    assert r.exit_code == 0, r.output
    (project / "audio" / "conv_0001.wav").unlink()
    r = runner.invoke(app, ["validate", str(project / "vakforge.jsonl")])
    assert r.exit_code == 1
    assert "audio.path" in flat(r)


def test_cp1252_console_does_not_crash_on_rupee_or_cross():
    import io

    from vakforge.cli import make_stream_safe

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    make_stream_safe(stream)
    stream.write("₹500 ✗ मेरा\n")
    stream.flush()
    assert raw.getvalue().startswith(b"?500 ? ????")


def test_recommend_from_folder_and_from_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "proj", "-l", "hi-Latn-IN"]).exit_code == 0
    raw = tmp_path / "proj" / "data" / "raw"
    (raw / "faq.md").write_text("Refund 5 din mein.\n\nMail help@acme.in", encoding="utf-8")
    (raw / "orders.csv").write_text("order_id,status\nA1,open\n", encoding="utf-8")
    r = runner.invoke(app, ["recommend", str(raw), "-o", "rec.json"])
    assert r.exit_code == 0, r.output
    assert "no" in r.output  # no conversations, so nothing to fine-tune on
    assert "evidence" in r.output  # and the verdict says what it rests on
    rec = json.loads((tmp_path / "rec.json").read_text(encoding="utf-8"))
    assert rec["locale"] == "hi-Latn-IN"
    assert rec["primary_problem"] == "tools"
    assert rec["fine_tune"] == "blocked"
    # Every goal is answered separately, each with its own bar and its own evidence.
    assert [g["goal"] for g in rec["goal_decisions"]] == rec["goals"]
    for decision in rec["goal_decisions"]:
        assert decision["eligibility"] in {"blocked", "baseline_first", "candidate"}
        assert decision["confidence"] in {"measured", "reported", "heuristic"}
        assert decision["evidence"]
    assert "goal · tools" in flat(r)

    assert runner.invoke(app, ["inspect", str(raw), "-o", "inspect.json"]).exit_code == 0
    r = runner.invoke(app, ["recommend", "inspect.json", "-g", "workflow", "--gpu", "24"])
    assert r.exit_code == 0, r.output
    assert "primary problem" in flat(r) and "workflow" in flat(r)


def test_out_paths_create_their_parent_directory(tmp_path, monkeypatch):
    # `-o reports/x.json` used to raise FileNotFoundError with a traceback.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "faq.md").write_text("Refund in 5 days.", encoding="utf-8")
    for args in (
        ["schema", "-o", "a/schema.json"],
        ["inspect", str(tmp_path), "-l", "en-US", "-o", "b/inspect.json"],
        ["recommend", "b/inspect.json", "-o", "c/rec.json"],
    ):
        r = runner.invoke(app, args)
        assert r.exit_code == 0, r.output
    for made in ("a/schema.json", "b/inspect.json", "c/rec.json"):
        assert (tmp_path / made).exists(), made


def test_recommend_reports_a_bad_locale_the_same_way_from_either_source(tmp_path):
    # Directory mode used to let the KeyError escape as a traceback, so the same bad
    # --locale printed a clean message from a report and a stack trace from a folder.
    (tmp_path / "r.json").write_text('{"locale": "en-US", "summary": {}}', encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.md").write_text("hello", encoding="utf-8")

    for source in ("r.json", "data"):
        r = runner.invoke(app, ["recommend", str(tmp_path / source), "-l", "xx-YY"])
        assert r.exit_code == 2, f"{source}: {r.output}"
        assert "unknown locale 'xx-YY'" in flat(r)
        assert "Traceback" not in r.output


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("{not json", "cannot read"),
        ('{"locale": "en-US"}', "no 'summary'"),
        # Valid JSON that is not an object used to reach report.get() and raise.
        ("[]", "holds JSON array, not an object"),
        ("null", "holds JSON null, not an object"),
        ("42", "holds JSON number, not an object"),
        # A summary of the wrong shape used to crash three functions into the rules.
        ('{"locale": "en-US", "summary": []}', "summary"),
        ('{"locale": "en-US", "summary": {"counts": 5}}', "summary.counts"),
        ('{"locale": "en-US", "summary": {"tool_candidates": "x"}}', "summary.tool_candidates"),
        # A locale that is not a string used to reach the pack lookup and die unhashable.
        ('{"locale": ["en-US"], "summary": {}}', "locale: must be a string, not JSON array"),
        ('{"locale": {"id": "en-US"}, "summary": {}}', "must be a string, not JSON object"),
        ('{"locale": true, "summary": {}}', "must be a string, not JSON boolean"),
    ],
)
def test_recommend_rejects_a_malformed_report_without_a_traceback(tmp_path, body, needle):
    (tmp_path / "r.json").write_text(body, encoding="utf-8")
    r = runner.invoke(app, ["recommend", str(tmp_path / "r.json")])
    assert r.exit_code == 2, r.output
    assert needle in flat(r)


def test_recommend_reads_a_report_saved_with_a_byte_order_mark(tmp_path):
    # What Windows PowerShell 5.1 writes after a user edits the report by hand.
    (tmp_path / "r.json").write_text('{"locale": "en-US", "summary": {}}', encoding="utf-8-sig")
    r = runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "-o", str(tmp_path / "o.json")])
    assert r.exit_code == 0, r.output


def test_recommend_says_when_nothing_is_usable(tmp_path):
    report = {"locale": "en-US", "summary": {"counts": {"table": 1}, "profiled": {"table": 1}}}
    (tmp_path / "r.json").write_text(json.dumps(report), encoding="utf-8")
    r = runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "-o", str(tmp_path / "o.json")])
    assert r.exit_code == 0, r.output
    assert "none yet: no usable evidence" in flat(r)
    assert "nothing usable yet" in flat(r)
    assert "facts belong in retrieval" not in flat(r)


def test_recommend_points_to_the_glossary(tmp_path):
    (tmp_path / "r.json").write_text('{"locale": "en-US", "summary": {}}', encoding="utf-8")
    r = runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "-o", str(tmp_path / "o.json")])
    assert "docs/glossary.html" in flat(r)


def test_recommend_marks_the_recipe_method_as_planned(tmp_path):
    report = {"locale": "en-US", "summary": {"counts": {"chat": 1}, "chat_messages": 900}}
    (tmp_path / "r.json").write_text(json.dumps(report), encoding="utf-8")
    args = ["recommend", str(tmp_path / "r.json"), "--gpu", "24"]
    r = runner.invoke(app, [*args, "-o", str(tmp_path / "o.json")])
    assert r.exit_code == 0, r.output
    assert "full fine-tune" in flat(r) and "(planned, not yet run)" in flat(r)


def test_recommend_rejects_bad_goal_and_gpu(tmp_path):
    (tmp_path / "r.json").write_text('{"locale": "en-US", "summary": {}}', encoding="utf-8")
    assert runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "-g", "magic"]).exit_code == 2
    assert runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "--gpu", "12"]).exit_code == 2


EXPECTED = Path(__file__).parents[2] / "examples" / "hinglish-shop" / "expected"


def test_report_writes_one_page_from_both_reports(tmp_path):
    out = tmp_path / "report.html"
    args = ["report", str(EXPECTED / "inspect.json"), str(EXPECTED / "recommend.json")]
    r = runner.invoke(app, [*args, "-o", str(out)])
    assert r.exit_code == 0, r.output
    page = out.read_text(encoding="utf-8")
    assert "<h2>Recommendation</h2>" in page
    assert "<h2>Files</h2>" in page


def test_report_works_from_inspect_alone(tmp_path):
    out = tmp_path / "report.html"
    r = runner.invoke(app, ["report", str(EXPECTED / "inspect.json"), "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert "<h2>Recommendation</h2>" not in out.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("inspect_body", "recommend_body", "needle"),
    [
        ("[]", None, "holds JSON array, not an object"),
        ('{"locale": "en-US"}', None, "no summary and files"),
        (None, '{"locale": "hi-Latn-IN"}', "no goal_decisions"),
        # A hand-edited summary: the page names the missing field instead of a traceback.
        ('{"locale": "en-US", "summary": {}, "files": []}', None, "cannot build the page"),
    ],
)
def test_report_rejects_a_malformed_file_without_a_traceback(
    tmp_path, inspect_body, recommend_body, needle
):
    inspect = EXPECTED / "inspect.json"
    if inspect_body is not None:
        inspect = tmp_path / "i.json"
        inspect.write_text(inspect_body, encoding="utf-8")
    args = ["report", str(inspect)]
    if recommend_body is not None:
        (tmp_path / "r.json").write_text(recommend_body, encoding="utf-8")
        args.append(str(tmp_path / "r.json"))
    r = runner.invoke(app, [*args, "-o", str(tmp_path / "o.html")])
    assert r.exit_code == 2, r.output
    assert needle in flat(r)
    assert not (tmp_path / "o.html").exists()


def test_report_warns_when_the_two_files_disagree_on_locale(tmp_path):
    rec = json.loads((EXPECTED / "recommend.json").read_text(encoding="utf-8"))
    rec["locale"] = "en-US"
    (tmp_path / "r.json").write_text(json.dumps(rec), encoding="utf-8")
    args = ["report", str(EXPECTED / "inspect.json"), str(tmp_path / "r.json")]
    r = runner.invoke(app, [*args, "-o", str(tmp_path / "o.html")])
    assert r.exit_code == 0, r.output
    assert "same folder" in flat(r)


def test_locales_lists_launch_packs():
    r = runner.invoke(app, ["locales"])
    assert r.exit_code == 0, r.output
    for pack_id in ("en-US", "en-GB", "en-IN", "hi-Latn-IN"):
        assert pack_id in flat(r)


def test_locales_show_resolves_inherited_settings():
    r = runner.invoke(app, ["locales", "hi-Latn-IN"])
    assert r.exit_code == 0, r.output
    assert "aadhaar" in flat(r)
    assert "notice_required" in flat(r)
    assert "lfm25-audio=understand_only" in flat(r)


def test_locales_unknown_pack():
    r = runner.invoke(app, ["locales", "xx-YY"])
    assert r.exit_code == 2
    assert "unknown locale pack" in flat(r)


def test_inspect_uses_project_locale_and_writes_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "proj", "-l", "hi-Latn-IN"]).exit_code == 0
    raw = tmp_path / "proj" / "data" / "raw"
    (raw / "faq.md").write_text("Refund 5 din mein.\n\nMail help@acme.in", encoding="utf-8")
    (raw / "deck.pptx").write_bytes(b"PK")
    r = runner.invoke(app, ["inspect", str(raw), "-o", "report.json"])
    assert r.exit_code == 0, r.output
    assert "email 1" in flat(r)
    assert "skipped deck.pptx" in flat(r)
    assert "0.0 min" in flat(r)  # no audio: minutes, not "0.0 h"
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["locale"] == "hi-Latn-IN"


def test_inspect_says_when_table_counts_come_from_a_sample(tmp_path, monkeypatch):
    from vakforge.inspect import profile

    monkeypatch.setattr(profile, "TABLE_SCAN_CHARS", 30)
    (tmp_path / "crm.csv").write_text("email\n" + "a@example.com\n" * 10, encoding="utf-8")
    (tmp_path / "more.csv").write_text("email\nb@example.com\n", encoding="utf-8")
    r = runner.invoke(
        app, ["inspect", str(tmp_path), "-l", "en-US", "-o", str(tmp_path / "i.json")]
    )
    assert r.exit_code == 0, r.output
    assert "2 tables" in flat(r)
    assert "(large files sampled)" in flat(r)


def test_inspect_without_locale_explains(tmp_path):
    r = runner.invoke(app, ["inspect", str(tmp_path)])
    assert r.exit_code == 2
    assert "pass --locale" in flat(r)


def test_schema_export(tmp_path):
    out = tmp_path / "s.json"
    r = runner.invoke(app, ["schema", "--out", str(out)])
    assert r.exit_code == 0
    assert json.loads(out.read_text())["title"].startswith("vakforge conversation")
