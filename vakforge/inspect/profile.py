"""Per-source facts for `inspect`. Deliberately shallow: enough for `recommend` to decide.

Documents: words, languages, PII counts. Tables: columns, rows, id-like columns (tool
candidates), PII counts per column. Chats: messages and speakers. Audio: duration, format,
clipping, silence.

Every number here is measured, never inferred. A low silence ratio, for example, is
reported as it is and not turned into a verdict of "noisy", because unbroken energy is
equally what dense speech looks like. Judgement calls belong to `recommend` and the agent
skill, which say what evidence they used.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np

from vakforge.inspect.sources import (
    _WHATSAPP_LINE,
    _WHATSAPP_STAMP,
    SPEAKER_KEYS,
    TEXT_KEYS,
    Source,
    column_key,
    conversation_pair,
    json_records,
    message_columns,
)
from vakforge.locales.base import LocalePack

_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"\w+", re.UNICODE)
# A schema or database prefix ("public.orders", "`shop`.`orders`") is matched and thrown
# away so the table keeps its own name. This stays a regex rather than a SQL parser: core
# has no parsing dependency, and the cost is that unusual quoting, computed defaults and
# constraint bodies are read approximately.
_CREATE_TABLE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
    r"(?:[`\"\[]?\w+[`\"\]]?\s*\.\s*)?"
    r"[`\"\[]?(\w+)",
    re.I,
)
_SQL_CONSTRAINT_WORDS = {
    "PRIMARY", "KEY", "UNIQUE", "CONSTRAINT", "FOREIGN", "INDEX", "FULLTEXT", "SPATIAL", "CHECK",
}  # fmt: skip
_ID_COLUMN = re.compile(r"(^id$|_id$|^id_|number$|_no$|^sku$|^email$|^phone$)", re.I)
MAX_CHARS = 2_000_000  # read at most this much text per file
# A JSON document cannot be read in part, so it gets its own, larger limit. It used to be
# MAX_CHARS, which turned away a 2 MB export; parsing 32 million characters takes a couple
# of seconds and roughly 150 MB, and anything bigger is better as JSONL anyway.
MAX_WHOLE_CHARS = 32_000_000
# Table cells are scanned one at a time, with the column name as context: about a second per
# million characters on real exports. At 200,000 a text-heavy table was judged on 163 of
# 26,872 rows, too few for "none found" to mean much; `rows_scanned` says what was covered.
TABLE_SCAN_CHARS = 1_000_000


class FileTooLarge(ValueError):
    """Raised for a file that only parses as a whole and is over `MAX_WHOLE_CHARS`.

    Truncating such a file and parsing the fragment produces a syntax error that blames the
    file's contents for a limit we imposed, so `inspect` says what really happened instead.
    """


def _read_text(path: Path) -> tuple[str, bool]:
    """Up to `MAX_CHARS` of text, and whether the file was longer than that."""
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read(MAX_CHARS + 1)
    return (text[:MAX_CHARS], True) if len(text) > MAX_CHARS else (text, False)


def _whole_text(path: Path) -> str:
    """Text of a file that has to be parsed in one piece, or `FileTooLarge`."""
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        text = fh.read(MAX_WHOLE_CHARS + 1)
    if len(text) > MAX_WHOLE_CHARS:
        raise FileTooLarge(
            f"over {MAX_WHOLE_CHARS:,} characters and must be parsed whole; "
            "split it or convert it to JSONL"
        )
    return text


def _text_facts(text: str, pack: LocalePack) -> dict[str, Any]:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    langs = Counter(pack.detect_lang(p) for p in paragraphs[:200])
    pii = Counter(span.type for span in pack.find_pii(text))
    return {
        "words": len(_WORD.findall(text)),
        "languages": dict(langs.most_common()),
        "pii": dict(pii.most_common()),
    }


def profile_document(src: Source, pack: LocalePack) -> dict[str, Any]:
    text, truncated = _read_text(src.path)
    if src.format in {"html", "htm"}:
        text = _TAG.sub(" ", text)
    facts = _text_facts(text, pack)
    if truncated:
        # Word and PII counts describe the part we read, so say so rather than let a
        # downstream reader treat them as whole-file totals.
        facts["truncated"] = True
    return facts


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    cols: dict[str, None] = {}
    for row in rows[:50]:
        cols.update(dict.fromkeys(row))
    return list(cols)


def _jsonl_rows(text: str, truncated: bool) -> tuple[list[Any], list[str]]:
    """One record per line, plus a message for each line that would not parse.

    A single malformed line used to fail the whole file, which contradicts the rule the
    rest of `inspect` follows: one bad part never aborts the run. Exports are routinely
    half-good, and the good half is still worth counting.

    A truncated read cuts the last line mid-way, so that one is dropped rather than
    reported as a fault in the data.
    """
    lines = text.splitlines()
    if truncated and lines:
        lines.pop()
    rows: list[Any] = []
    errors: list[str] = []
    for n, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"line {n}: {exc.msg}")
    return rows, errors


def _record_cells(record: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, str]]:
    """Every scalar in a JSON record as (column, text); nested keys join with a dot."""
    for key, value in record.items():
        name = f"{prefix}{key}"
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                yield from _record_cells(item, f"{name}.")
            elif isinstance(item, str | int | float) and not isinstance(item, bool):
                yield name, str(item)


# Personal data no pattern can see: a name or an address has no fixed shape, but a CRM
# column says what it holds. Deliberately narrow: a bare `name` is as often a product's (the
# example shop's catalogue has one) as a person's, and `username` is a handle, so neither
# counts; a false alarm on every catalogue would teach people to ignore the column.
_NAME_HEADERS = {
    "full_name", "first_name", "last_name", "middle_name", "given_name", "family_name",
    "surname", "customer_name", "client_name", "contact_name", "caller_name", "patient_name",
    "member_name", "holder_name", "account_holder_name", "cardholder_name", "sender_name",
    "recipient_name", "agent_name", "employee_name", "staff_name", "rep_name",
}  # fmt: skip
_ADDRESS_HEADER = re.compile(
    r"^(?:(?:home|billing|shipping|postal|mailing|street|residential|delivery|customer)_)?"
    r"address(?:_line)?_?\d?$"
)
_DOB_HEADERS = {"dob", "date_of_birth", "birth_date", "birthdate", "birthday"}


def _header_pii(column: str) -> str | None:
    """The kind of personal data a column holds by its name alone, if the name says."""
    key = column_key(column)
    if key in _NAME_HEADERS:
        return "person_name"
    if _ADDRESS_HEADER.match(key):
        return "address"
    return "date_of_birth" if key in _DOB_HEADERS else None


def _table_pii(rows: Iterable[Iterable[tuple[str, str]]], pack: LocalePack) -> dict[str, Any]:
    """Personal data in a table's cells, by column, from the rows that fit TABLE_SCAN_CHARS.

    A CRM export keeps its phone numbers and emails in cells, so reading only the header
    reported "none found" for exactly the files most likely to hold some. Each cell is
    scanned with its column name in front, as the context a lone cell lacks: ten digits in
    `order_id` then read as a reference, as they would in a sentence, and an `ssn` column
    supplies the cue a bare nine-digit number needs.
    """
    by_column: dict[str, Counter[str]] = {}
    cues: dict[str, str] = {}
    by_header: dict[str, str | None] = {}
    scanned = chars = 0
    for cells in rows:
        if chars > TABLE_SCAN_CHARS:
            break
        scanned += 1
        for column, value in cells:
            chars += len(value)
            if column not in cues:
                cues[column] = re.sub(r"[\W_]+", " ", column).strip() + ": "
                by_header[column] = _header_pii(column)
            if by_header[column] and value.strip():
                by_column.setdefault(column, Counter())[by_header[column]] += 1
            cue = cues[column]
            for span in pack.find_pii(cue + value):
                if span.start >= len(cue):  # a match inside the column name is not data
                    by_column.setdefault(column, Counter())[span.type] += 1
    total: Counter[str] = sum(by_column.values(), Counter())
    return {
        "pii": dict(total.most_common()),
        "pii_columns": {col: dict(n.most_common()) for col, n in by_column.items()},
        "rows_scanned": scanned,
    }


def profile_table(src: Source, pack: LocalePack) -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {}
    truncated = False
    parse_errors: list[str] = []
    pii: Counter[str] = Counter()
    if src.format in {"csv", "tsv"}:
        with src.path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t" if src.format == "tsv" else ",")
            n_rows = 0

            def cells() -> Iterator[list[tuple[str, str]]]:
                nonlocal n_rows
                for row in reader:
                    n_rows += 1
                    # Surplus fields land under the key None as a list; they have no column.
                    yield [(c, v) for c, v in row.items() if c and isinstance(v, str) and v]

            scan = _table_pii(cells(), pack)
            # Counted, not collected: a large CRM export should not have to fit in memory
            # to be counted, including the rows past the scanning budget.
            n_rows += sum(1 for _ in reader)
        tables[src.path.stem] = {"columns": reader.fieldnames or [], "rows": n_rows, **scan}
    elif src.format == "sql":
        sql, truncated = _read_text(src.path)
        for match in _CREATE_TABLE.finditer(sql):
            body = sql[match.end() : sql.find(";", match.end())]
            cols = re.findall(r"^\s*[`\"\[]?(\w+)[`\"\]]?\s+\w+", body, re.M)
            # "PRIMARY KEY (...)" and "KEY idx_x (...)" have the shape of a column line; the
            # Sakila schema listed PRIMARY, KEY and CONSTRAINT as columns of every table.
            cols = [c for c in cols if c.upper() not in _SQL_CONSTRAINT_WORDS]
            tables[match.group(1)] = {"columns": cols, "rows": None}
        # A dump's INSERT statements carry the data; it is scanned as text, like a document.
        pii.update(span.type for span in pack.find_pii(sql))
    else:
        if src.format == "json":
            rows = json_records(json.loads(_whole_text(src.path)))
        else:  # jsonl / ndjson records
            text, truncated = _read_text(src.path)
            rows, parse_errors = _jsonl_rows(text, truncated)
        rows = [r for r in rows if isinstance(r, dict)]
        scan = _table_pii((_record_cells(r) for r in rows), pack)
        tables[src.path.stem] = {"columns": _columns_from_rows(rows), "rows": len(rows), **scan}
    for name, t in tables.items():
        # Matched on the key, not the header: a real export says "Ticket ID", and read
        # literally that matched nothing, so an 8,000-ticket table offered no tools.
        t["id_columns"] = [c for c in t["columns"] if _ID_COLUMN.search(column_key(c))]
        t["tool_candidates"] = [
            f"lookup_{column_key(name)}_by_{column_key(c)}" for c in t["id_columns"][:3]
        ]
        pii.update(t.pop("pii", {}))
    facts: dict[str, Any] = {"tables": tables, "pii": dict(pii.most_common())}
    if truncated:
        facts["truncated"] = True  # row counts cover the part we read, not the whole file
    if parse_errors:
        facts["parse_errors"] = parse_errors  # counted rows exclude these
    return facts


def _csv_messages(
    src: Source, pack: LocalePack, speakers: Counter[str], messages: list[str]
) -> tuple[int, dict[str, Any]]:
    """Messages from a CSV in either chat layout: every one counted, their text sampled.

    One exchange per row (a user column and a reply column), or one message per row (a
    speaker column and a text column). Counting streams the whole file, so a million-row
    export is counted in full; the text kept for languages and personal data stops at
    MAX_CHARS, as it does for any file.

    The other columns of the sampled rows are scanned as table cells are: a conversation
    export often carries `customer_name` beside the messages, and reading only the message
    text lost it. Returns the count and the facts about which columns were read.
    """
    total = chars = 0
    others: list[list[tuple[str, str]]] = []

    def keep(who: str, body: str) -> None:
        nonlocal total, chars
        if not body.strip():
            return
        total += 1
        speakers[who] += 1
        if chars < MAX_CHARS:
            messages.append(body)
            chars += len(body)

    def rest(row: dict[str, Any], used: tuple[str, ...]) -> None:
        if chars < MAX_CHARS:
            others.append(
                [(c, v) for c, v in row.items() if c and c not in used and isinstance(v, str) and v]
            )

    with src.path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t" if src.format == "tsv" else ",")
        fields = reader.fieldnames or []
        if pair := conversation_pair(fields):
            read_as: dict[str, Any] = {"pair": list(pair)}
            for row in reader:
                rest(row, pair)
                for col in pair:
                    keep(col, row.get(col) or "")
        else:
            speaker, text = message_columns(fields) or ("", "")
            read_as = {"message_columns": [speaker, text]}
            for row in reader:
                rest(row, (speaker, text))
                keep((row.get(speaker) or "?").strip() or "?", row.get(text) or "")
    scan = _table_pii(others, pack)
    if scan["pii_columns"]:
        read_as["pii_columns"] = scan["pii_columns"]
        read_as["column_pii"] = scan["pii"]  # merged into the file's pii by the caller
    return total, read_as


def profile_chat(src: Source, pack: LocalePack) -> dict[str, Any]:
    speakers: Counter[str] = Counter()
    messages: list[str] = []
    truncated = False
    parse_errors: list[str] = []
    counted: int | None = None  # set when every message is counted but not every one read
    read_as: dict[str, Any] = {}  # which columns held the conversation
    if src.format in {"csv", "tsv"}:
        counted, read_as = _csv_messages(src, pack, speakers, messages)
    elif src.format == "whatsapp":
        text, truncated = _read_text(src.path)
        for line in text.splitlines():
            if m := _WHATSAPP_LINE.match(line):
                speaker = m.group("speaker").strip()
                speakers[speaker] += 1
                messages.append(line[m.end() :])
            elif _WHATSAPP_STAMP.match(line):
                continue  # a system notice, not anyone's message and not a continuation
            elif messages:
                # A message that wrapped onto its own line carries no timestamp header; it
                # belongs to the message above, and dropping it loses most long messages.
                messages[-1] += "\n" + line
    else:
        records: list[Any] = []
        if src.format == "json":
            records += json_records(json.loads(_whole_text(src.path)))
        else:
            text, truncated = _read_text(src.path)
            rows, parse_errors = _jsonl_rows(text, truncated)
            for row in rows:
                records += row if isinstance(row, list) else [row]
        for rec in records:
            if isinstance(rec, dict) and "messages" not in rec and (cols := conversation_pair(rec)):
                read_as = {"pair": list(cols)}
                for col in cols:
                    if rec.get(col):
                        speakers[col] += 1
                        messages.append(str(rec[col]))
                continue
            turns = rec.get("messages", [rec]) if isinstance(rec, dict) else []
            for turn in turns:
                who = next((turn[k] for k in SPEAKER_KEYS if k in turn), "?")
                body = next((turn[k] for k in TEXT_KEYS if k in turn), "")
                speakers[str(who)] += 1
                messages.append(str(body))
    facts = _text_facts("\n\n".join(messages), pack)
    facts.update(
        messages=len(messages) if counted is None else counted,
        speakers=dict(speakers.most_common(10)),
    )
    if column_pii := read_as.pop("column_pii", None):
        facts["pii"] = dict((Counter(facts["pii"]) + Counter(column_pii)).most_common())
    facts.update(read_as)  # "pair" or "message_columns": which columns were read
    if counted is not None and len(messages) < counted:
        facts["messages_scanned"] = len(messages)  # languages and PII cover these only
    if truncated:
        facts["truncated"] = True  # message count covers the part we read
    if parse_errors:
        facts["parse_errors"] = parse_errors  # counted messages exclude these
    return facts


STATS_SECONDS = 600  # silence and clipping are measured over at most this much audio


def profile_audio(src: Source, pack: LocalePack) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(str(src.path))
    # Read at most the first ten minutes: the statistics below are indicative, and a long
    # recording should not have to fit in memory to be described.
    frames = min(info.frames, info.samplerate * STATS_SECONDS)
    data, sr = sf.read(str(src.path), dtype="float32", always_2d=True, frames=frames)
    mono = data.mean(axis=1)
    frame = max(1, sr // 50)  # 20 ms
    n = len(mono) // frame
    rms = (
        np.sqrt((mono[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
        if n
        else np.array([])
    )
    silence = float((20 * np.log10(rms) < -40).mean()) if n else 1.0
    clipping = float((np.abs(data) >= 0.999).mean()) if data.size else 0.0
    sampled = round(frames / info.samplerate, 2) if info.samplerate else 0.0
    return {
        "duration_s": round(info.duration, 2),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        # True for telephone-band audio, which limits which models can be trained on it.
        "narrowband": info.samplerate <= 8000,
        "clipping_ratio": round(clipping, 5),
        "silence_ratio": round(silence, 3),
        # The ratios above describe `stats_sampled_s`, which is not always `duration_s`.
        # Printing a whole-file duration beside head-only statistics invites reading them
        # as whole-file measurements.
        "stats_sampled_s": sampled,
        "stats_partial": sampled < round(info.duration, 2),
    }


PROFILERS = {
    "document": profile_document,
    "table": profile_table,
    "chat": profile_chat,
    "audio": profile_audio,
}
