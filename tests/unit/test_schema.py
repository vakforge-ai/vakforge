import pytest
from pydantic import ValidationError

from tests.conftest import conversation
from vakforge.schema import Conversation, json_schema


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


def test_json_schema_export_is_draft_2020():
    s = json_schema()
    assert s["$schema"].endswith("2020-12/schema")
    assert "turns" in s["properties"]
