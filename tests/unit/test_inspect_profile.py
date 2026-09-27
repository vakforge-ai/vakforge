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


def test_an_html_page_is_read_as_a_reader_sees_it(tmp_path):
    # A saved company page counted its CSS and JavaScript as prose: 15,616 "words" for 854
    # visible ones, and a CSS line height (1.4285714286) as a phone number.
    p = tmp_path / "page.html"
    p.write_text(
        "<html><head><title>Acme</title><style>p{line-height:1.4285714286}</style>"
        "<script>var config = {tracking: 'abc', retries: 3};</script></head><body>"
        "<!-- hidden note: call 415-555-0134 -->"
        "<h1>Returns &amp; refunds</h1><p>Refunds take five days.</p>"
        "<p>Call us on 415-555-0199.</p><svg><text>logo text</text></svg></body></html>",
        encoding="utf-8",
    )
    facts = profile_document(classify(p), get_pack("en-US"))
    assert (
        facts["words"] == 12
    )  # Returns refunds / Refunds take five days / Call us on 415 555 0199
    assert facts["pii"] == {"phone": 1}  # the visible one; not the comment, not the CSS
    assert facts["languages"] == {"en-US": 3}  # three paragraphs, not one


def test_csv_columns_rows_and_tool_candidates(tmp_path):
    p = tmp_path / "orders.csv"
    p.write_text("order_id,customer_id,status\nA1,C1,open\nA2,C2,closed\n", encoding="utf-8")
    t = profile_table(classify(p), HI)["tables"]["orders"]
    assert t["rows"] == 2
    assert t["id_columns"] == ["order_id", "customer_id"]
    assert t["tool_candidates"][0] == "lookup_orders_by_order_id"


def test_id_columns_are_found_however_the_export_spells_them(tmp_path):
    # A real CRM export: title case and spaces. Read literally this matched nothing, and an
    # 8,469-ticket table offered no tools at all.
    p = tmp_path / "Support Tickets.csv"
    p.write_text("Ticket ID,Customer-ID,Order No,Status\n1,C1,A9,open\n", encoding="utf-8")
    t = profile_table(classify(p), HI)["tables"]["Support Tickets"]
    assert t["id_columns"] == ["Ticket ID", "Customer-ID", "Order No"]
    assert t["tool_candidates"] == [
        "lookup_support_tickets_by_ticket_id",
        "lookup_support_tickets_by_customer_id",
        "lookup_support_tickets_by_order_no",
    ]


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
        "pii_columns": {},
        "rows_scanned": 2,
        "id_columns": ["sku"],
        "tool_candidates": ["lookup_catalog_by_sku"],
    }


def test_table_cells_are_scanned_for_personal_data_by_column(tmp_path):
    # A CRM export used to report "none found": only the header was ever read.
    p = tmp_path / "customers.csv"
    p.write_text(
        "customer_id,mobile,email,order_id\n"
        "C1,98765 43219,asha@example.com,9876543210\n"
        "C2,+91 91234 56780,ravi@example.org,9123456780\n",
        encoding="utf-8",
    )
    facts = profile_table(classify(p), HI)
    t = facts["tables"]["customers"]
    assert t["pii_columns"] == {"mobile": {"phone": 2}, "email": {"email": 2}}
    assert t["rows_scanned"] == 2
    # Ten digits under order_id are a reference, as "order id 9876543210" is in a sentence.
    assert facts["pii"] == {"phone": 2, "email": 2}


def test_names_addresses_and_birth_dates_are_found_by_their_column(tmp_path):
    # No pattern can see a name; a support-ticket export's "Customer Name" went unflagged.
    p = tmp_path / "crm.csv"
    p.write_text(
        "Customer Name,Billing Address,DOB,Product Name,Name,Username\n"
        "Asha Verma,12 MG Road,1990-01-02,Inverter X,Inverter X,asha90\n"
        "Ravi Rao,,1985-05-06,Battery Y,Battery Y,ravi85\n",
        encoding="utf-8",
    )
    t = profile_table(classify(p), HI)["tables"]["crm"]
    assert t["pii_columns"] == {
        "Customer Name": {"person_name": 2},
        "Billing Address": {"address": 1},  # an empty cell holds nobody's address
        "DOB": {"date_of_birth": 2},
    }


def test_a_column_name_supplies_the_cue_a_bare_number_needs(tmp_path):
    p = tmp_path / "people.csv"
    p.write_text("ssn,zip_plus_four\n536221234,536221234\n", encoding="utf-8")
    t = profile_table(classify(p), get_pack("en-US"))["tables"]["people"]
    assert t["pii_columns"] == {"ssn": {"ssn": 1}}


def test_nested_json_records_are_scanned_with_dotted_columns(tmp_path):
    p = tmp_path / "crm.json"
    p.write_text(
        json.dumps([{"id": 1, "contact": {"phone": "9876543219", "emails": ["a@b.co"]}}]),
        encoding="utf-8",
    )
    t = profile_table(classify(p), HI)["tables"]["crm"]
    assert t["pii_columns"] == {"contact.phone": {"phone": 1}, "contact.emails": {"email": 1}}


def test_sql_dump_rows_are_scanned(tmp_path):
    p = tmp_path / "dump.sql"
    p.write_text(
        "CREATE TABLE users (\n  id INT,\n  email TEXT\n);\n"
        "INSERT INTO users VALUES (1, 'priya@example.in');\n",
        encoding="utf-8",
    )
    assert profile_table(classify(p), HI)["pii"] == {"email": 1}


def test_rows_past_the_scan_budget_are_still_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "TABLE_SCAN_CHARS", 30)
    p = tmp_path / "big.csv"
    p.write_text("email\n" + "someone@example.com\n" * 10, encoding="utf-8")
    t = profile_table(classify(p), HI)["tables"]["big"]
    assert t["rows"] == 10
    assert t["rows_scanned"] < 10  # says the scan saw part of the table, not all of it


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


def test_a_json_file_over_the_text_limit_is_still_read_whole(tmp_path, monkeypatch):
    # A 2.1 MB export used to be turned away at the 2,000,000-character text limit.
    monkeypatch.setattr(profile, "MAX_CHARS", 200)
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps([{"sku": f"X{i}"} for i in range(200)]), encoding="utf-8")
    assert profile_table(classify(p), HI)["tables"]["catalog"]["rows"] == 200


def test_oversized_json_is_skipped_with_its_real_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "MAX_WHOLE_CHARS", 200)
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


def test_a_csv_of_exchanges_is_read_as_messages(tmp_path):
    p = tmp_path / "pairs.csv"
    p.write_text(
        "input,output\n"
        "Mera order kab aayega?,Kal tak aa jayega.\n"
        "Refund kab milega?,Paanch din mein aa jayega.\n"
        "Theek hai thanks,\n",  # an empty reply is not a message
        encoding="utf-8",
    )
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 5
    assert facts["speakers"] == {"input": 3, "output": 2}
    assert facts["pair"] == ["input", "output"]
    assert "hi-Latn" in facts["languages"]
    assert "messages_scanned" not in facts  # all of it was read


def test_every_exchange_is_counted_but_only_a_sample_is_read(tmp_path, monkeypatch):
    # A million-row export is counted in full; its text is sampled like any large file.
    monkeypatch.setattr(profile, "MAX_CHARS", 40)
    p = tmp_path / "pairs.csv"
    p.write_text("input,output\n" + "Where is my order?,On its way.\n" * 20, encoding="utf-8")
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 40
    assert 0 < facts["messages_scanned"] < 40


def test_a_csv_with_one_message_per_row_is_read_as_messages(tmp_path):
    # The layout of a public support-conversations export (976,271 rows), which was read
    # as a table and offered "lookup by conv_id" as its only use.
    p = tmp_path / "conversations.csv"
    p.write_text(
        "conv_id,turn_index,Role,Text,customer_name,agent_name\n"
        "c1,0,customer,Mera order kab aayega?,Asha,Meena\n"
        "c1,1,agent,Kal tak aa jayega.,Asha,Meena\n"
        "c1,2,customer,,Asha,Meena\n"  # an empty message is not one
        "c2,0,customer,Refund kab milega?,Ravi,Meena\n",
        encoding="utf-8",
    )
    src = classify(p)
    assert src.kind == "chat"
    facts = profile_chat(src, HI)
    assert facts["messages"] == 3
    assert facts["speakers"] == {"customer": 2, "agent": 1}
    assert facts["message_columns"] == ["Role", "Text"]
    assert "hi-Latn" in facts["languages"]
    # The name columns beside the messages are still personal data; an agent is a person.
    assert facts["pii_columns"] == {
        "customer_name": {"person_name": 4},
        "agent_name": {"person_name": 4},
    }
    assert facts["pii"]["person_name"] == 8


def test_json_records_of_exchanges_are_read_as_messages(tmp_path):
    p = tmp_path / "train.json"
    rows = [{"instruction": "cancel my order", "response": "Done.", "intent": "cancel"}] * 3
    p.write_text(json.dumps(rows), encoding="utf-8")
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 6
    assert facts["pair"] == ["instruction", "response"]


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("faq.csv", "Question,Answer\nRefund kab milega?,Paanch din mein.\nCOD?,Haan ji.\n"),
        (
            "faq.json",  # JSON Lines under a .json name, as a public FAQ dataset ships it
            '{"question": "Refund kab milega?", "answer": "Paanch din mein."}\n'
            '{"question": "COD?", "answer": "Haan ji."}\n',
        ),
    ],
)
def test_an_faq_is_read_as_the_text_it_is(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    src = classify(p)
    assert src.kind == "document"
    facts = profile_document(src, HI)
    assert facts["faq_pairs"] == 2
    assert facts["words"] > 5
    assert "hi-Latn" in facts["languages"]


def test_a_jsonl_faq_cut_short_by_the_read_limit_says_so(tmp_path, monkeypatch):
    # Long fields beside the question and answer used up the limit, so fewer pairs were
    # read than the file holds, and the count was reported as a total.
    monkeypatch.setattr(profile, "MAX_CHARS", 2000)
    rows = [{"question": f"Q{i}?", "answer": f"A{i}.", "notes": "x" * 200} for i in range(50)]
    p = tmp_path / "faq.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    facts = profile_document(classify(p), HI)
    assert facts["faq_pairs"] < 50
    assert facts["truncated"] is True


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


def test_a_whatsapp_export_with_long_messages_is_still_a_chat(tmp_path):
    # A real export: a system notice first, with no sender, and messages that run over many
    # lines, so only one of the first 20 lines carried a timestamp. It was read as a document.
    long_message = "".join(f"line {i} of a long message\n" for i in range(25))
    p = tmp_path / "WhatsApp Chat with Priya.txt"
    p.write_text(
        "26/09/2026, 9:18 am - Messages and calls are end-to-end encrypted.\n"
        f"26/09/2026, 9:19 am - Priya: {long_message}"
        f"26/09/2026, 9:20 am - Asha: {long_message}"
        "26/09/2026, 9:21 am - Priya: ok\n",
        encoding="utf-8",
    )
    src = classify(p)
    assert (src.kind, src.format) == ("chat", "whatsapp")
    facts = profile_chat(src, HI)
    assert facts["messages"] == 3
    assert facts["speakers"] == {"Priya": 2, "Asha": 1}


def test_bracketed_whatsapp_export_names_the_speaker(tmp_path):
    # iOS exports use "[date, time] Name:" with no dash. Recovering the name by splitting
    # on " - " gave speakers called "[12/03/24, 10:15] Priya".
    p = tmp_path / "export.txt"
    p.write_text(
        "[12/03/24, 10:15] Priya: Order kab aayega?\n"
        "[12/03/24, 10:16] Acme Support: Kal tak\n"
        "[12/03/24, 10:17] Priya: Theek hai\n",
        encoding="utf-8",
    )
    facts = profile_chat(classify(p), HI)
    assert facts["speakers"] == {"Priya": 2, "Acme Support": 1}


def test_sql_constraint_lines_are_not_columns(tmp_path):
    # Shaped like the public Sakila schema, which listed PRIMARY, KEY and CONSTRAINT as
    # columns of every table.
    p = tmp_path / "schema.sql"
    p.write_text(
        "CREATE TABLE customer (\n"
        "  customer_id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,\n"
        "  email VARCHAR(50) DEFAULT NULL,\n"
        "  PRIMARY KEY  (customer_id),\n"
        "  KEY idx_email (email),\n"
        "  UNIQUE KEY uq (email),\n"
        "  CONSTRAINT fk_customer FOREIGN KEY (customer_id) REFERENCES x (id)\n"
        ");",
        encoding="utf-8",
    )
    assert profile_table(classify(p), HI)["tables"]["customer"]["columns"] == [
        "customer_id",
        "email",
    ]


def test_schema_qualified_sql_table_keeps_its_own_name(tmp_path):
    p = tmp_path / "schema.sql"
    p.write_text(
        "CREATE TABLE public.orders (\n  order_id INT\n);\n"
        'CREATE TABLE IF NOT EXISTS "shop"."customers" (\n  id INT\n);\n'
        "CREATE TABLE tickets (\n  ticket_id INT\n);",
        encoding="utf-8",
    )
    assert list(profile_table(classify(p), HI)["tables"]) == ["orders", "customers", "tickets"]


def test_one_bad_jsonl_line_does_not_lose_the_file(tmp_path):
    # One bad record used to raise, marking the whole export unreadable. Every other part
    # of inspect keeps going and records what it skipped; this now does too.
    p = tmp_path / "rows.jsonl"
    p.write_text('{"sku": "A"}\n{BROKEN\n{"sku": "B"}\n', encoding="utf-8")
    facts = profile_table(classify(p), HI)
    assert facts["tables"]["rows"]["rows"] == 2
    assert len(facts["parse_errors"]) == 1
    assert facts["parse_errors"][0].startswith("line 2:")


def test_a_bad_line_in_a_chat_export_is_reported_too(tmp_path):
    # profile_table reported these and profile_chat silently dropped them, because it
    # iterated the (rows, errors) tuple instead of unpacking it. Every chat fixture was
    # well-formed, so nothing failed.
    p = tmp_path / "chat.jsonl"
    p.write_text(
        json.dumps({"role": "user", "content": "Order kab aayega?"}) + "\n"
        "{BROKEN\n" + json.dumps({"role": "assistant", "content": "Kal tak."}) + "\n",
        encoding="utf-8",
    )
    facts = profile_chat(classify(p), HI)
    assert facts["messages"] == 2
    assert facts["parse_errors"][0].startswith("line 2:")


def test_audio_statistics_say_how_much_they_cover(tmp_path):
    # Head-only statistics printed beside a whole-file duration read as whole-file numbers.
    p = write_wav(tmp_path / "short.wav", seconds=2.0)
    facts = profile_audio(classify(p), HI)
    assert facts["stats_sampled_s"] == facts["duration_s"]
    assert facts["stats_partial"] is False


def test_a_long_recording_is_flagged_as_only_partly_measured(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "STATS_SECONDS", 1)
    p = write_wav(tmp_path / "long.wav", seconds=3.0)
    facts = profile_audio(classify(p), HI)
    assert facts["duration_s"] == 3.0
    assert facts["stats_sampled_s"] == 1.0
    assert facts["stats_partial"] is True


def test_a_clean_jsonl_file_reports_no_parse_errors(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"sku": "A"}\n{"sku": "B"}\n', encoding="utf-8")
    assert "parse_errors" not in profile_table(classify(p), HI)


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


@pytest.mark.parametrize(
    ("name", "subtype"),
    [
        ("voice-note.opus", "OPUS"),  # a WhatsApp voice note: Ogg Opus
        ("article.oga", "VORBIS"),  # Wikimedia's name for Ogg audio
    ],
)
def test_opus_and_oga_are_read_as_audio(tmp_path, name, subtype):
    # Both were turned away, .opus with advice to convert a file that needed no converting.
    p = tmp_path / name
    t = np.linspace(0, 1, 48000, endpoint=False, dtype=np.float32)
    sf.write(str(p), 0.3 * np.sin(2 * np.pi * 300 * t), 48000, format="OGG", subtype=subtype)
    src = classify(p)
    assert (src.kind, src.readable) == ("audio", True)
    assert profile_audio(src, HI)["duration_s"] == pytest.approx(1.0, abs=0.05)


def test_phone_band_audio_marked_narrowband(tmp_path):
    p = tmp_path / "phone.wav"
    t = np.linspace(0, 1, 8000, endpoint=False, dtype=np.float32)
    sf.write(str(p), np.concatenate([0.3 * np.sin(2 * np.pi * 300 * t), np.zeros(8000)]), 8000)
    facts = profile_audio(classify(p), HI)
    assert facts["narrowband"] is True
    assert 0.4 < facts["silence_ratio"] < 0.6


def test_a_table_of_labelled_texts_is_recognised(tmp_path):
    # An intent dataset: one text per row and its category, no id column.
    p = tmp_path / "intents.csv"
    p.write_text("text,category\nwhere is my order,order_status\ncancel it,cancel\n", "utf-8")
    table = profile_table(classify(p), HI)["tables"]["intents"]
    assert table["labelled_texts"] == ["text", "category"]
    q = tmp_path / "tickets.csv"
    q.write_text("ticket_id,text,category\n1,late,delivery\n", "utf-8")
    assert "labelled_texts" not in profile_table(classify(q), HI)["tables"]["tickets"]
