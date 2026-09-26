import json

import pytest

from tests.conftest import write_wav
from vakforge.inspect.sources import discover


def _make_tree(root):
    (root / "docs").mkdir()
    (root / "docs" / "faq.md").write_text("# FAQ\nHow do I reset?", encoding="utf-8")
    (root / "docs" / "policy.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "tables").mkdir()
    (root / "tables" / "orders.csv").write_text("order_id,status\nA1,open\n", encoding="utf-8")
    (root / "tables" / "schema.sql").write_text("CREATE TABLE t (id int);", encoding="utf-8")
    (root / "tables" / "catalog.json").write_text(json.dumps([{"sku": "X", "price": 5}]))
    (root / "tables" / "prices.xlsx").write_bytes(b"PK fake")
    (root / "chats").mkdir()
    (root / "chats" / "support.jsonl").write_text(
        json.dumps({"role": "user", "content": "hi"}) + "\n", encoding="utf-8"
    )
    (root / "chats" / "export.txt").write_text(
        "12/03/24, 10:15 - Priya: Hello\n12/03/24, 10:16 - Agent: Hi\n"
        "12/03/24, 10:17 - Priya: Order status?\n",
        encoding="utf-8",
    )
    write_wav(root / "calls" / "call1.wav")
    (root / "calls" / "call2.m4a").write_bytes(b"fake")
    (root / ".DS_Store").write_bytes(b"x")
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref")
    (root / "notes.bin").write_bytes(b"\x00")


def test_discover_classifies_every_kind(tmp_path):
    _make_tree(tmp_path)
    got = {
        s.path.relative_to(tmp_path).as_posix(): (s.kind, s.format, s.readable)
        for s in discover(tmp_path)
    }
    assert got == {
        "calls/call1.wav": ("audio", "wav", True),
        "calls/call2.m4a": ("audio", "m4a", False),
        "chats/export.txt": ("chat", "whatsapp", True),
        "chats/support.jsonl": ("chat", "jsonl", True),
        "docs/faq.md": ("document", "md", True),
        "docs/policy.pdf": ("document", "pdf", False),
        "notes.bin": ("other", "bin", False),
        "tables/catalog.json": ("table", "json", True),
        "tables/orders.csv": ("table", "csv", True),
        "tables/prices.xlsx": ("table", "xlsx", False),
        "tables/schema.sql": ("table", "sql", True),
    }


def test_unreadable_sources_explain_what_to_do(tmp_path):
    _make_tree(tmp_path)
    notes = {s.path.name: s.note for s in discover(tmp_path) if not s.readable and s.note}
    assert notes["call2.m4a"] == "convert to WAV or FLAC first"
    assert notes["prices.xlsx"] == "export to CSV to profile"


@pytest.mark.parametrize(
    ("name", "body", "kind"),
    [
        # One exchange per row: conversations, not a lookup table. Read as a table, a
        # million-row export of them was reported as "nothing yet".
        ("pairs.csv", "input,output\nOrder kab aayega?,Kal tak.\n", "chat"),
        # Question and answer is an FAQ: knowledge, read as a document.
        ("faq.csv", "Question,Answer\nRefund?,5 days.\n", "document"),
        ("train.tsv", "instruction\tcategory\tresponse\nhi\tX\thello\n", "chat"),
        ("orders.csv", "order_id,status\nA1,open\n", "table"),
        ("labels.csv", "text,category\nwhere is my card,card_arrival\n", "table"),
    ],
)
def test_a_csv_of_exchanges_is_a_chat(tmp_path, name, body, kind):
    (tmp_path / name).write_text(body, encoding="utf-8")
    [src] = discover(tmp_path)
    assert src.kind == kind


def test_json_lines_saved_as_json_are_read_as_json_lines(tmp_path):
    # A public FAQ dataset ships train.json with one record per line; parsed as a single
    # document it failed on its second line.
    rows = [{"question": "How do I pay?", "answer": "By card or UPI."}] * 3
    (tmp_path / "train.json").write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    [src] = discover(tmp_path)
    assert (src.kind, src.format) == ("document", "jsonl")  # question/answer: an FAQ


def test_records_nested_under_a_key_are_found(tmp_path):
    body = {"questions": [{"question": "Refund?", "answer": "5 days."}]}
    (tmp_path / "faq.json").write_text(json.dumps(body), encoding="utf-8")
    [src] = discover(tmp_path)
    assert src.kind == "document"


def test_a_large_json_chat_is_not_taken_for_a_table(tmp_path):
    # Only the first 20,000 characters are read to classify; that head is not valid JSON
    # on its own, so every JSON chat export larger than that used to become a table.
    turns = [{"role": "user", "content": "Order kab aayega? " * 20}] * 400
    (tmp_path / "support.json").write_text(json.dumps(turns), encoding="utf-8")
    assert (tmp_path / "support.json").stat().st_size > 20_000
    [src] = discover(tmp_path)
    assert src.kind == "chat"


def test_json_records_of_exchanges_are_a_chat(tmp_path):
    rows = [{"instruction": "cancel my order", "response": "Done.", "intent": "cancel"}]
    (tmp_path / "train.json").write_text(json.dumps(rows), encoding="utf-8")
    [src] = discover(tmp_path)
    assert (src.kind, src.format) == ("chat", "json")
