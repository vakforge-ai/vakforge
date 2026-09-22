import json

import numpy as np
import pytest
import soundfile as sf

from tests.conftest import write_wav
from vakforge.inspect import profile
from vakforge.inspect.profile import (
    profile_audio,
    profile_chat,
    profile_document,
    profile_table,
)
from vakforge.inspect.sources import classify
from vakforge.locales import get_pack

HI = get_pack("hi-Latn-IN")


def test_document_words_languages_and_pii(tmp_path):
    p = tmp_path / "faq.md"
    p.write_text(
        "Refunds take 5 days.\n\nHaan ji, refund 5 din mein aata hai.\n\n"
        "Call +91 98765 43210 or mail help@acme.in",
        encoding="utf-8",
    )
    facts = profile_document(classify(p), HI)
    assert facts["words"] > 10
    assert facts["languages"] == {"en-IN": 2, "hi-Latn": 1}
    assert facts["pii"] == {"phone": 1, "email": 1}


def test_csv_columns_rows_and_tool_candidates(tmp_path):
    p = tmp_path / "orders.csv"
    p.write_text("order_id,customer_id,status\nA1,C1,open\nA2,C2,closed\n", encoding="utf-8")
    t = profile_table(classify(p), HI)["tables"]["orders"]
    assert t["rows"] == 2
    assert t["id_columns"] == ["order_id", "customer_id"]
    assert t["tool_candidates"][0] == "lookup_orders_by_order_id"


def test_sql_schema_tables(tmp_path):
    p = tmp_path / "schema.sql"
    p.write_text(
        "CREATE TABLE tickets (\n  ticket_id INT,\n  status TEXT\n);\n"
        'CREATE TABLE IF NOT EXISTS "customers" (\n  id INT,\n  phone TEXT\n);',
        encoding="utf-8",
    )
    tables = profile_table(classify(p), HI)["tables"]
    assert tables["tickets"]["columns"] == ["ticket_id", "status"]
    assert tables["customers"]["id_columns"] == ["id", "phone"]


def test_json_records(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({"items": [{"sku": "X1", "price": 5}, {"sku": "X2", "price": 7}]}))
    t = profile_table(classify(p), HI)["tables"]["catalog"]
    assert t == {
        "columns": ["sku", "price"],
        "rows": 2,
        "id_columns": ["sku"],
        "tool_candidates": ["lookup_catalog_by_sku"],
    }


def test_jsonl_chat(tmp_path):
    p = tmp_path / "support.jsonl"
    p.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Order kab aayega?"},
                    {"role": "assistant", "content": "Kal tak aa jayega."},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 2
    assert facts["speakers"] == {"user": 1, "assistant": 1}


def test_oversized_json_is_skipped_with_its_real_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "MAX_CHARS", 200)
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps([{"sku": f"X{i}"} for i in range(200)]), encoding="utf-8")
    with pytest.raises(profile.FileTooLarge, match="must be parsed whole"):
        profile_table(classify(p), HI)


def test_oversized_jsonl_keeps_whole_lines_and_says_it_was_cut(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "MAX_CHARS", 200)
    p = tmp_path / "rows.jsonl"
    p.write_text("".join(json.dumps({"sku": f"X{i}"}) + "\n" for i in range(50)), encoding="utf-8")
    facts = profile_table(classify(p), HI)
    assert facts["truncated"] is True
    assert 0 < facts["tables"]["rows"]["rows"] < 50


def test_whatsapp_chat(tmp_path):
    p = tmp_path / "export.txt"
    p.write_text(
        "12/03/24, 10:15 - Priya: Order kab aayega?\n"
        "12/03/24, 10:16 - Acme Support: Kal tak.\n"
        "12/03/24, 10:17 - Priya: Theek hai, thanks\n",
        encoding="utf-8",
    )
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 3
    assert facts["speakers"] == {"Priya": 2, "Acme Support": 1}
    assert "hi-Latn" in facts["languages"]


def test_whatsapp_multi_line_message_is_kept_whole(tmp_path):
    # Only the first line of a wrapped message carries a timestamp; the rest would
    # otherwise be dropped, which loses most of every long message in an export.
    p = tmp_path / "export.txt"
    p.write_text(
        "12/03/24, 10:15 - Priya: Address note kar lijiye:\n"
        "Flat 4B, MG Road\n"
        "Bangalore 560001\n"
        "12/03/24, 10:16 - Acme Support: Theek hai\n"
        "12/03/24, 10:17 - Priya: Thanks\n",
        encoding="utf-8",
    )
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 3
    assert facts["words"] > 10  # the two wrapped lines counted, not discarded


def test_audio_stats(tmp_path):
    p = write_wav(tmp_path / "call.wav", seconds=2.0, channels=2)
    facts = profile_audio(classify(p), HI)
    assert facts["duration_s"] == 2.0
    assert facts["channels"] == 2
    assert facts["narrowband"] is False
    assert facts["clipping_ratio"] == 0.0
    assert facts["silence_ratio"] < 0.05


def test_audio_facts_are_measurements_not_verdicts(tmp_path):
    # Two channels do not prove one is the user and the other the agent, and continuous
    # energy does not prove noise, so neither claim is reported.
    p = write_wav(tmp_path / "call.wav", seconds=2.0, channels=2)
    facts = profile_audio(classify(p), HI)
    assert "stereo_split_possible" not in facts
    assert "condition_guess" not in facts


def test_phone_band_audio_marked_narrowband(tmp_path):
    p = tmp_path / "phone.wav"
    t = np.linspace(0, 1, 8000, endpoint=False, dtype=np.float32)
    sf.write(str(p), np.concatenate([0.3 * np.sin(2 * np.pi * 300 * t), np.zeros(8000)]), 8000)
    facts = profile_audio(classify(p), HI)
    assert facts["narrowband"] is True
    assert 0.4 < facts["silence_ratio"] < 0.6
