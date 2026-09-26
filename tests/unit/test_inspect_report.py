import json

from tests.conftest import write_wav
from vakforge.inspect.report import inspect_dir, write_report
from vakforge.locales import get_pack


def _data(root):
    (root / "faq.md").write_text("Refund in 5 din.\n\nMail help@acme.in", encoding="utf-8")
    (root / "orders.csv").write_text("order_id,status\nA1,open\n", encoding="utf-8")
    (root / "chat.jsonl").write_text(
        json.dumps({"role": "user", "content": "Order kab aayega?"}) + "\n", encoding="utf-8"
    )
    write_wav(root / "call.wav", seconds=3.6, channels=2)
    (root / "broken.csv").write_bytes(b"a,b\n\x00\xff\n")
    (root / "bad.json").write_text("{not json", encoding="utf-8")
    (root / "slides.pptx").write_bytes(b"PK")


def test_summary_counts_and_totals(tmp_path):
    _data(tmp_path)
    s = inspect_dir(tmp_path, get_pack("hi-Latn-IN"))["summary"]
    assert s["counts"] == {"document": 2, "table": 3, "chat": 1, "audio": 1, "other": 0}
    assert s["chat_messages"] == 1
    assert s["audio_hours"] == 0.001  # 3.6 s
    assert s["two_channel_audio_files"] == 1
    assert s["pii"] == {"email": 1}
    assert "lookup_orders_by_order_id" in s["tool_candidates"]


def test_profiled_count_separates_found_from_understood(tmp_path):
    # slides.pptx and bad.json are found but never profiled; the totals below them come
    # only from the files that were, so both counts have to be visible.
    _data(tmp_path)
    s = inspect_dir(tmp_path, get_pack("hi-Latn-IN"))["summary"]
    assert s["counts"]["document"] == 2 and s["profiled"]["document"] == 1
    assert s["counts"]["table"] == 3 and s["profiled"]["table"] == 2
    assert s["unreadable"] == 2  # slides.pptx and bad.json


def test_bad_file_is_recorded_not_fatal(tmp_path):
    _data(tmp_path)
    files = {f["path"]: f for f in inspect_dir(tmp_path, get_pack("en-IN"))["files"]}
    assert files["bad.json"]["readable"] is False
    assert files["bad.json"]["error"].startswith("JSONDecodeError")
    assert files["slides.pptx"]["note"] == "text extraction not in core yet"
    assert files["orders.csv"]["facts"]["tables"]["orders"]["rows"] == 1


def test_a_limit_we_set_is_reported_in_plain_words(tmp_path, monkeypatch):
    # "FileTooLarge: over ..." named an internal class to a user who could do nothing with it.
    from vakforge.inspect import profile

    monkeypatch.setattr(profile, "MAX_WHOLE_CHARS", 10)
    (tmp_path / "big.json").write_text(json.dumps([{"id": i} for i in range(50)]), "utf-8")
    [f] = inspect_dir(tmp_path, get_pack("en-US"))["files"]
    assert f["error"].startswith("over 10 characters and must be parsed whole")


def test_report_round_trips_as_utf8_json(tmp_path):
    (tmp_path / "hi.md").write_text("मेरा ऑर्डर कहाँ है", encoding="utf-8")
    report = inspect_dir(tmp_path, get_pack("hi-Latn-IN"))
    out = write_report(report, tmp_path.parent / "inspect.json")
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["languages"] == {"hi": 1}


def test_tool_candidates_deduplicated_across_sources(tmp_path):
    (tmp_path / "orders.csv").write_text("order_id\nA1\n", encoding="utf-8")
    (tmp_path / "schema.sql").write_text(
        "CREATE TABLE orders (\n  order_id INT\n);", encoding="utf-8"
    )
    s = inspect_dir(tmp_path, get_pack("en-US"))["summary"]
    assert s["tool_candidates"] == ["lookup_orders_by_order_id"]


def test_utf8_bom_from_windows_tools_is_ignored(tmp_path):
    bom = "﻿"
    (tmp_path / "orders.csv").write_text(bom + "order_id,status\nA1,open\n", encoding="utf-8")
    (tmp_path / "chat.txt").write_text(
        bom + "15/09/26, 09:02 - Rahul: Order kab aayega?\n"
        "15/09/26, 09:03 - Shop: Kal tak\n15/09/26, 09:05 - Rahul: Theek hai\n",
        encoding="utf-8",
    )
    report = inspect_dir(tmp_path, get_pack("hi-Latn-IN"))
    s = report["summary"]
    assert s["counts"]["chat"] == 1
    assert s["chat_messages"] == 3
    assert s["tool_candidates"] == ["lookup_orders_by_order_id"]
