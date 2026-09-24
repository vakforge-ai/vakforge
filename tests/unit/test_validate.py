import json
from pathlib import Path

import pytest

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


def _redacted_row(**turn_over) -> dict:
    """A row that claims to be redacted, with one turn you can poison."""
    row = conversation(audio=None)
    turn = {"speaker": "user", "start": 0.0, "end": 1.0, "text": "All set.", "lang": "en-US"}
    turn.update(turn_over)
    row["turns"] = [turn]
    row["meta"] = dict(row["meta"], pii_redacted=True)
    return row


def test_a_redaction_claim_is_rescanned_not_trusted(tmp_path):
    # The exact hole: real PII in the text, pii_redacted true, and a log path that is a
    # plain lie. Every structural rule passes, so only a rescan catches it.
    row = _redacted_row(text="my ssn is 536221234 and my card is 4111 1111 1111 1111")
    row["meta"] = dict(
        row["meta"],
        source="real",
        consent="written",
        consent_ref="f.pdf",
        voice_consent_ref="v.pdf",
        redaction_log="does/not/exist.json",
    )
    _, issues = validate_manifest(_write(tmp_path, row))
    fields = {i.field for i in issues}
    assert "meta.redaction_log" in fields
    assert "turns[0].text" in fields
    found = {
        i.message.split("but ")[1].split(" is still")[0] for i in issues if "but " in i.message
    }
    assert found == {"ssn", "card_number"}


def test_a_leak_is_reported_without_repeating_it(tmp_path):
    # Reporting a leak must not copy the personal data into a log or a bug report.
    row = _redacted_row(text="call me on 415-555-0134")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert issues, "expected the phone number to be caught"
    for i in issues:
        assert "415" not in str(i), str(i)
    assert "phone is still present at characters" in issues[0].message


def test_pii_hiding_in_tool_arguments_is_caught(tmp_path):
    row = _redacted_row(
        speaker="agent",
        end=0.0,
        text=None,
        lang=None,
        tool_call={
            "id": "c1",
            "name": "book_appointment",
            "arguments": {"customer_id": "A-1", "callback": "415-555-0134"},
        },
    )
    _, issues = validate_manifest(_write(tmp_path, row))
    assert any(i.field == "turns[0].tool_call.arguments" for i in issues), [i.field for i in issues]


def test_redaction_log_must_be_a_real_log(tmp_path):
    (tmp_path / "log.json").write_text('{"notes": "trust me"}', encoding="utf-8")
    row = _redacted_row()
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert [i.field for i in issues] == ["meta.redaction_log"]
    assert "unreadable or malformed" in issues[0].message


@pytest.mark.parametrize(
    "escape",
    [
        "../outside.json",
        "a/../../outside.json",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "D:outside.json",
    ],
)
def test_the_redaction_log_cannot_point_outside_the_dataset(tmp_path, escape):
    # A manifest is data — generated, downloaded, handed over with a dataset. Every path it
    # carries is resolved against its own directory, so one that climbs out turns validate
    # into a file-existence oracle for the machine running it.
    row = _redacted_row()
    row["meta"] = dict(row["meta"], redaction_log=escape)
    _, issues = validate_manifest(_write(tmp_path, row))
    assert issues, f"{escape} was accepted"
    assert any("redaction_log" in i.message or "redaction_log" in i.field for i in issues)


def test_a_symlinked_redaction_log_that_leaves_the_dataset_is_rejected(tmp_path):
    # The string check cannot see this one: the path is relative and has no '..'.
    outside = tmp_path.parent / "outside-log.json"
    outside.write_text('{"spans": []}', encoding="utf-8")
    ds = tmp_path / "ds"
    ds.mkdir()
    try:
        (ds / "log.json").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privileges on this platform")
    row = _redacted_row()
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(ds, row))
    assert [i.field for i in issues] == ["meta.redaction_log"]
    assert "outside the dataset" in issues[0].message


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privileges on this platform")


def test_an_audio_symlink_that_leaves_the_dataset_is_rejected(tmp_path):
    # The containment check covered redaction logs and was forgotten for audio, which is
    # the file validate actually opens and decodes.
    outside = write_wav(tmp_path / "elsewhere" / "call.wav", channels=2)
    ds = tmp_path / "ds"
    (ds / "audio").mkdir(parents=True)
    _symlink_or_skip(ds / "audio" / "conv_0001.wav", outside)
    _, issues = validate_manifest(_write(ds, conversation()))
    assert [i.field for i in issues] == ["audio.path"]
    assert "outside the dataset" in issues[0].message


def test_an_audio_symlink_that_stays_inside_the_dataset_is_fine(tmp_path):
    ds = tmp_path / "ds"
    real = write_wav(ds / "store" / "call.wav", channels=2)
    (ds / "audio").mkdir()
    _symlink_or_skip(ds / "audio" / "conv_0001.wav", real)
    _, issues = validate_manifest(_write(ds, conversation()))
    assert issues == []


def test_a_log_from_another_conversation_is_not_evidence(tmp_path):
    (tmp_path / "log.json").write_text(
        json.dumps({"conversation_id": "someone_else", "spans": []}), encoding="utf-8"
    )
    row = _redacted_row()
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert [i.field for i in issues] == ["meta.redaction_log"]
    assert "not this one" in issues[0].message


def test_a_span_must_describe_a_redaction_that_happened(tmp_path):
    (tmp_path / "log.json").write_text(
        json.dumps({"spans": [{"type": "ssn", "turn": 0, "placeholder": "<SSN_1>"}]}),
        encoding="utf-8",
    )
    row = _redacted_row(text="nothing was removed here")  # no placeholder in the text
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert [i.field for i in issues] == ["meta.redaction_log"]
    assert "does not contain it" in issues[0].message


def test_a_span_pointing_at_a_turn_that_does_not_exist_is_rejected(tmp_path):
    (tmp_path / "log.json").write_text(
        json.dumps({"spans": [{"type": "ssn", "turn": 9}]}), encoding="utf-8"
    )
    row = _redacted_row()
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert "does not exist" in issues[0].message


def test_an_empty_span_list_is_accepted(tmp_path):
    # A conversation may genuinely contain no personal data. The substantive proof is the
    # rescan of the text, not the length of the log.
    (tmp_path / "log.json").write_text('{"spans": []}', encoding="utf-8")
    row = _redacted_row(text="nothing sensitive here at all")
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert issues == []


def test_a_properly_redacted_row_passes(tmp_path):
    (tmp_path / "log.json").write_text(
        json.dumps({"spans": [{"turn": 0, "type": "ssn", "placeholder": "<SSN_1>"}]}),
        encoding="utf-8",
    )
    row = _redacted_row(text="my ssn is <SSN_1>, thanks")
    row["meta"] = dict(row["meta"], redaction_log="log.json")
    _, issues = validate_manifest(_write(tmp_path, row))
    assert issues == []


def test_unredacted_rows_are_not_rescanned(tmp_path):
    # pii_redacted=false claims nothing, so there is nothing to disprove. Consent still is.
    row = _redacted_row(text="my ssn is 536221234")
    row["meta"] = dict(row["meta"], pii_redacted=False)
    _, issues = validate_manifest(_write(tmp_path, row))
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


def test_lang_mix_tags_are_held_to_the_pack_too(project):
    row = conversation(audio=None, locale="hi-Latn-IN")
    row["turns"] = [
        {
            "speaker": "user",
            "start": 0.0,
            "end": 1.0,
            "text": "haan",
            "lang": "hi-Latn",
            "lang_mix": ["hi-Latn", "fr-FR"],
        }
    ]
    _, issues = validate_manifest(_write(project, row))
    assert [i.field for i in issues] == ["turns[0].lang_mix"]
    assert "'fr-FR' is not declared" in issues[0].message


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
