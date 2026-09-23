import json

from typer.testing import CliRunner

from vakforge import __version__
from vakforge.cli import app
from vakforge.config import ProjectConfig

runner = CliRunner()


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


def test_init_rejects_unknown_locale(tmp_path):
    r = runner.invoke(app, ["init", str(tmp_path / "x"), "--locale", "xx-YY"])
    assert r.exit_code == 2
    assert "unknown locale" in r.output


def test_validate_exit_codes(project):
    r = runner.invoke(app, ["validate", str(project / "vakforge.jsonl")])
    assert r.exit_code == 0, r.output
    (project / "audio" / "conv_0001.wav").unlink()
    r = runner.invoke(app, ["validate", str(project / "vakforge.jsonl")])
    assert r.exit_code == 1
    assert "audio.path" in r.output


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
    assert rec["evidence_confidence"] in {"measured", "reported", "heuristic"}

    assert runner.invoke(app, ["inspect", str(raw), "-o", "inspect.json"]).exit_code == 0
    r = runner.invoke(app, ["recommend", "inspect.json", "-g", "workflow", "--gpu", "24"])
    assert r.exit_code == 0, r.output
    assert "primary problem" in r.output and "workflow" in r.output


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


def test_recommend_rejects_bad_goal_and_gpu(tmp_path):
    (tmp_path / "r.json").write_text('{"locale": "en-US", "summary": {}}', encoding="utf-8")
    assert runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "-g", "magic"]).exit_code == 2
    assert runner.invoke(app, ["recommend", str(tmp_path / "r.json"), "--gpu", "12"]).exit_code == 2


def test_locales_lists_launch_packs():
    r = runner.invoke(app, ["locales"])
    assert r.exit_code == 0, r.output
    for pack_id in ("en-US", "en-GB", "en-IN", "hi-Latn-IN"):
        assert pack_id in r.output


def test_locales_show_resolves_inherited_settings():
    r = runner.invoke(app, ["locales", "hi-Latn-IN"])
    assert r.exit_code == 0, r.output
    assert "aadhaar" in r.output
    assert "notice_required" in r.output
    assert "lfm25-audio=understand_only" in r.output


def test_locales_unknown_pack():
    r = runner.invoke(app, ["locales", "xx-YY"])
    assert r.exit_code == 2
    assert "unknown locale pack" in r.output


def test_inspect_uses_project_locale_and_writes_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init", "proj", "-l", "hi-Latn-IN"]).exit_code == 0
    raw = tmp_path / "proj" / "data" / "raw"
    (raw / "faq.md").write_text("Refund 5 din mein.\n\nMail help@acme.in", encoding="utf-8")
    (raw / "deck.pptx").write_bytes(b"PK")
    r = runner.invoke(app, ["inspect", str(raw), "-o", "report.json"])
    assert r.exit_code == 0, r.output
    assert "email 1" in r.output
    assert "skipped deck.pptx" in r.output
    assert "0.0 min" in r.output  # no audio: minutes, not "0.0 h"
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["locale"] == "hi-Latn-IN"


def test_inspect_without_locale_explains(tmp_path):
    r = runner.invoke(app, ["inspect", str(tmp_path)])
    assert r.exit_code == 2
    assert "pass --locale" in r.output


def test_schema_export(tmp_path):
    out = tmp_path / "s.json"
    r = runner.invoke(app, ["schema", "--out", str(out)])
    assert r.exit_code == 0
    assert json.loads(out.read_text())["title"].startswith("vakforge conversation")
