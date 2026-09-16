import json
from pathlib import Path

from tests.conftest import conversation, write_wav
from vakforge.validate import validate_manifest


def _write(root: Path, *rows: dict) -> Path:
    m = root / "vakforge.jsonl"
    m.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return m


def test_clean_manifest_has_no_issues(project):
    convs, issues = validate_manifest(project / "vakforge.jsonl")
    assert len(convs) == 1
    assert issues == []


def test_missing_audio_file(tmp_path):
    m = _write(tmp_path, conversation())
    _, issues = validate_manifest(m)
    assert [i.field for i in issues] == ["audio.path"]
    assert "does not exist" in issues[0].message


def test_audio_declaration_mismatch(tmp_path):
    write_wav(tmp_path / "audio" / "conv_0001.wav", channels=1, seconds=4.0, sr=16000)
    m = _write(tmp_path, conversation())
    _, issues = validate_manifest(m)
    assert {i.field for i in issues} == {"audio.sample_rate", "audio.channels", "audio.duration_s"}


def test_unknown_locale_and_undeclared_lang(project):
    bad = conversation(locale="xx-YY")
    bad["audio"] = None
    other = conversation(id="conv_0002")
    other["audio"] = None
    other["turns"][0]["lang"] = "hi-Latn"
    m = _write(project, bad, other)
    _, issues = validate_manifest(m)
    fields = {(i.conv_id, i.field) for i in issues}
    assert ("conv_0001", "locale") in fields
    assert ("conv_0002", "turns[0].lang") in fields


def test_tool_arguments_checked_against_json_schema(project):
    row = conversation()
    row["audio"] = None
    row["turns"][2]["tool_call"]["arguments"] = {}
    m = _write(project, row)
    _, issues = validate_manifest(m)
    assert issues[0].field == "turns[2].tool_call.arguments"
    assert "customer_id" in issues[0].message


def test_consent_none_requires_flag(project):
    row = conversation()
    row["audio"] = None
    row["meta"]["consent"] = "none"
    m = _write(project, row)
    _, issues = validate_manifest(m)
    assert [i.field for i in issues] == ["meta.consent"]
    _, issues = validate_manifest(m, allow_unconsented=True)
    assert issues == []


def test_bad_json_line_and_duplicate_id(project):
    row = conversation()
    row["audio"] = None
    m = project / "vakforge.jsonl"
    m.write_text(json.dumps(row) + "\n{not json\n" + json.dumps(row) + "\n", encoding="utf-8")
    _, issues = validate_manifest(m)
    assert [(i.line, i.field) for i in issues] == [(2, "json"), (3, "id")]


def test_splits_json_must_agree(project):
    (project / "splits.json").write_text(
        json.dumps({"train": [], "test": ["conv_0001"], "seed": 1})
    )
    _, issues = validate_manifest(project / "vakforge.jsonl")
    assert [i.field for i in issues] == ["meta.split"]
