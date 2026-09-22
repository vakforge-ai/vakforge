import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.conftest import conversation
from vakforge.schema import Conversation, json_schema

DATA_FORMAT = Path(__file__).parents[2] / "docs" / "DATA_FORMAT.md"


def test_the_documented_example_record_is_valid():
    # The example is what people copy. Its entity offsets were wrong before the schema
    # started checking them, and nothing would have caught that.
    block = re.search(r"```json\n(\{.*?\n\})\n```", DATA_FORMAT.read_text(encoding="utf-8"), re.S)
    assert block, "docs/DATA_FORMAT.md no longer contains a JSON example"
    Conversation.model_validate(json.loads(block.group(1)))


def test_valid_record_parses(valid_conv):
    conv = Conversation.model_validate(valid_conv)
    assert conv.id == "conv_0001"
    assert conv.turns[2].tool_call.name == "book_appointment"
    assert not conv.turns[2].spoken


def test_audio_optional_for_text_only_records(valid_conv):
    valid_conv["audio"] = None
    Conversation.model_validate(valid_conv)


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda c: c["turns"][0].update(text=""), "non-empty text"),
        (lambda c: c["turns"][0].pop("lang"), "need lang"),
        (lambda c: c["turns"][1].update(start=5.0, end=5.5), "sorted by start"),
        (lambda c: c["turns"][0].update(end=-1.0), "greater than or equal to 0"),
        (lambda c: c["turns"][3]["tool_result"].update(id="nope"), "unknown call id"),
        (lambda c: c["turns"][2]["tool_call"].update(name="nope"), "not declared in tools"),
        (lambda c: c["turns"][2].update(speaker="user"), "speaker='agent'"),
        (lambda c: c["audio"].pop("channel_map"), "needs channel_map"),
        (lambda c: c["audio"].update(duration_s=1.0), "audio.duration_s"),
        (lambda c: c["meta"].update(consent="verbal"), "consent"),
        (lambda c: c.update(extra_field=1), "extra_field"),
    ],
)
def test_invalid_records_fail_with_actionable_message(mutate, needle):
    data = conversation()
    mutate(data)
    with pytest.raises(ValidationError) as exc:
        Conversation.model_validate(data)
    assert needle in str(exc.value)


def test_duplicate_tool_call_ids_rejected():
    data = conversation()
    data["turns"].append(
        {
            "speaker": "agent",
            "start": 2.0,
            "end": 2.0,
            "tool_call": {"id": "c1", "name": "book_appointment", "arguments": {}},
        }
    )
    with pytest.raises(ValidationError, match="duplicate tool_call id"):
        Conversation.model_validate(data)


def test_duplicate_tool_names_rejected():
    data = conversation()
    data["tools"].append({"name": "book_appointment", "description": "a second, different one"})
    with pytest.raises(ValidationError, match="duplicate tool name"):
        Conversation.model_validate(data)


@pytest.mark.parametrize(
    "path",
    ["../../etc/passwd", "audio/../../secrets.wav", "/etc/passwd", "C:\\Windows\\win.ini"],
)
def test_audio_path_cannot_escape_the_dataset(path):
    # audio.path is resolved against the manifest's directory, and a manifest is data.
    data = conversation()
    data["audio"]["path"] = path
    with pytest.raises(ValidationError, match="audio.path must"):
        Conversation.model_validate(data)


def test_stereo_channel_map_must_name_both_speakers():
    data = conversation()
    data["audio"]["channel_map"] = {"0": "user", "1": "user"}
    with pytest.raises(ValidationError, match="one channel to 'user'"):
        Conversation.model_validate(data)


@pytest.mark.parametrize(
    ("entity", "needle"),
    [
        ({"type": "id", "text": "A-1", "start_char": 9}, "both start_char and end_char"),
        ({"type": "id", "text": "A-1", "start_char": 0, "end_char": 3}, "not 'A-1'"),
        ({"type": "id", "text": "A-1", "start_char": 9, "end_char": 400}, "past the end"),
        ({"type": "id", "text": "A-1", "start_char": 9, "end_char": 2}, "start_char=9"),
    ],
)
def test_entity_offsets_must_point_at_the_entity(entity, needle):
    data = conversation()
    data["turns"][1]["entities"] = [entity]
    with pytest.raises(ValidationError, match=needle):
        Conversation.model_validate(data)


def test_correct_entity_offsets_pass():
    data = conversation()
    text = data["turns"][1]["text"]  # "Book me, ID A-1."
    start = text.index("A-1")
    data["turns"][1]["entities"] = [
        {"type": "customer_id", "text": "A-1", "start_char": start, "end_char": start + 3}
    ]
    Conversation.model_validate(data)


@pytest.mark.parametrize(
    ("meta", "needle"),
    [
        ({"consent": "written", "consent_ref": None}, "needs consent_ref"),
        ({"consent": "recorded_verbal", "consent_ref": None}, "needs consent_ref"),
        ({"source": "public", "consent": "public_license"}, "needs license"),
        ({"source": "real", "consent": "written", "consent_ref": "f.pdf"}, "must be redacted"),
        ({"consent": "synthetic", "source": "real"}, "only valid with source='synthetic'"),
    ],
)
def test_consent_and_redaction_claims_need_evidence(meta, needle):
    data = conversation()
    data["meta"].update(meta)
    data["meta"].setdefault("pii_redacted", True)
    if meta.get("source") == "real":
        data["meta"]["pii_redacted"] = False
    with pytest.raises(ValidationError, match=needle):
        Conversation.model_validate(data)


def test_a_redaction_claim_on_real_data_needs_a_log():
    data = conversation()
    data["meta"].update(
        source="real", consent="written", consent_ref="forms/2026-01.pdf", pii_redacted=True
    )
    data["audio"] = None
    with pytest.raises(ValidationError, match="needs redaction_log"):
        Conversation.model_validate(data)


def test_real_recordings_need_separate_consent_for_the_voice():
    # A voiceprint is biometric data; consent to record a call is not consent to train a
    # voice on it.
    data = conversation()
    data["meta"].update(
        source="real",
        consent="written",
        consent_ref="forms/2026-01.pdf",
        pii_redacted=True,
        redaction_log="logs/redaction-0001.json",
    )
    with pytest.raises(ValidationError, match="voice_consent_ref"):
        Conversation.model_validate(data)
    data["meta"]["voice_consent_ref"] = "forms/voice-2026-01.pdf"
    Conversation.model_validate(data)


def test_json_schema_export_is_draft_2020():
    s = json_schema()
    assert s["$schema"].endswith("2020-12/schema")
    assert "turns" in s["properties"]
