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


def test_schema_export(tmp_path):
    out = tmp_path / "s.json"
    r = runner.invoke(app, ["schema", "--out", str(out)])
    assert r.exit_code == 0
    assert json.loads(out.read_text())["title"].startswith("vakforge conversation")
