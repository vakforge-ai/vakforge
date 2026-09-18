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
    assert s["audio_hours"] == 0.0
    assert s["stereo_audio_files"] == 1
    assert s["pii"] == {"email": 1}
    assert "lookup_orders_by_order_id" in s["tool_candidates"]


def test_bad_file_is_recorded_not_fatal(tmp_path):
    _data(tmp_path)
    files = {f["path"]: f for f in inspect_dir(tmp_path, get_pack("en-IN"))["files"]}
    assert files["bad.json"]["readable"] is False
    assert files["bad.json"]["error"].startswith("JSONDecodeError")
    assert files["slides.pptx"]["note"] == "text extraction not in core yet"
    assert files["orders.csv"]["facts"]["tables"]["orders"]["rows"] == 1


def test_report_round_trips_as_utf8_json(tmp_path):
    (tmp_path / "hi.md").write_text("मेरा ऑर्डर कहाँ है", encoding="utf-8")
    report = inspect_dir(tmp_path, get_pack("hi-Latn-IN"))
    out = write_report(report, tmp_path.parent / "inspect.json")
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["languages"] == {"hi": 1}
