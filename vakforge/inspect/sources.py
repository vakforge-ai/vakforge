"""Walk a data folder and sort each file into a source kind."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Kind = Literal["document", "table", "chat", "audio", "other"]

DOCUMENT_EXT = {".txt", ".md", ".markdown", ".html", ".htm", ".rst"}
BINARY_DOCUMENT_EXT = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".pptx"}
TABLE_EXT = {".csv", ".tsv", ".sql"}
BINARY_TABLE_EXT = {".xlsx", ".xls", ".ods", ".parquet"}
AUDIO_EXT = {".wav", ".flac", ".ogg", ".mp3"}
UNREADABLE_AUDIO_EXT = {".m4a", ".aac", ".wma", ".opus", ".amr"}
JSON_EXT = {".json", ".jsonl", ".ndjson"}

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".ipynb_checkpoints"}

# WhatsApp export line: "12/03/24, 10:15 - Name: text", or the bracketed variant
# "[12/03/24, 10:15] Name: text" that iOS exports use. The name is captured here rather
# than recovered by splitting the match afterwards: the bracketed form has no " - " to
# split on, so that approach produced speakers called "[12/03/24, 10:15] Priya".
# iOS exports may open a line with a left-to-right mark, which is invisible but not a digit.
_STAMP = r"^‎?\[?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4},? \d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]\.?m\.?)?\]?"
_WHATSAPP_LINE = re.compile(_STAMP + r"\s?[-–]?\s?(?P<speaker>[^:]{1,60}): ", re.I)
# A timestamp with no sender: a system line ("Messages and calls are end-to-end encrypted").
_WHATSAPP_STAMP = re.compile(_STAMP, re.I)


def column_key(name: object) -> str:
    """A column name as a comparable key: "Ticket ID" and "ticket-id" both read "ticket_id".

    Exports from Excel and CRMs title-case and space their headers, so every rule that
    recognises a column by its name has to look through that.
    """
    return re.sub(r"[^0-9a-z]+", "_", str(name).lower()).strip("_")


# Column (or key) pairs that hold one exchange per row: what the user said, then the reply.
# Support exports and training sets name them many ways; these are the common ones. A CSV
# with such a pair is conversations, not a lookup table, and read as one it was ignored.
CONVERSATION_PAIRS = (
    ("input", "output"),
    ("instruction", "response"),
    ("question", "answer"),
    ("query", "response"),
    ("prompt", "response"),
    ("prompt", "completion"),
    ("customer", "agent"),
    ("user", "assistant"),
    ("user", "agent"),
    ("user", "bot"),
)


def conversation_pair(names: Iterable[object]) -> tuple[str, str] | None:
    """The (user, reply) columns among `names`, in the file's own spelling, or None."""
    by_key = {column_key(n): str(n) for n in names}
    for user, reply in CONVERSATION_PAIRS:
        if user in by_key and reply in by_key:
            return by_key[user], by_key[reply]
    return None


def _csv_header(path: Path, delimiter: str) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            return next(csv.reader(fh, delimiter=delimiter), [])
    except (OSError, csv.Error):
        return []


@dataclass(frozen=True)
class Source:
    """One file and what vakforge thinks it is."""

    path: Path
    kind: Kind
    format: str
    readable: bool = True
    note: str = ""


def json_records(data: Any) -> list[Any]:
    """The records of a parsed JSON document: a top-level list, or the first list inside a
    wrapper object ({"questions": [...]}), or the object itself."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return next((v for v in data.values() if isinstance(v, list)), [data])
    return []


def _head(path: Path) -> str:
    try:
        with path.open(encoding="utf-8-sig") as fh:
            return fh.read(20_000)
    except (OSError, UnicodeDecodeError):
        return ""


def _is_json_lines(head: str) -> bool:
    """One JSON record per line, whatever the file is called. Exports often save JSON Lines
    as `.json`, and parsed as one document the file failed on its second line."""
    lines = [line for line in head.splitlines() if line.strip()][:2]
    if len(lines) < 2:
        return False
    try:
        return all(isinstance(json.loads(line), dict) for line in lines)
    except json.JSONDecodeError:
        return False


def _head_records(head: str) -> list[Any]:
    """The first few records of a JSON document from its opening characters alone.

    The head of a large export is not valid JSON by itself, so parsing it whole meant any
    JSON chat file over 20,000 characters was taken for a table. Records are decoded one
    at a time from the first array instead.
    """
    text = head.lstrip()
    try:
        return json_records(json.loads(text))[:5]
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    if start < 0:
        return []
    decoder, i, records = json.JSONDecoder(), start + 1, []
    while len(records) < 5:
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text) or text[i] == "]":
            break
        try:
            record, i = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        records.append(record)
    return records


def _looks_like_chat_json(head: str, lines: bool) -> bool:
    """JSON or JSONL whose records carry role/speaker + content/text, a `messages` list, or
    a user/reply pair of fields."""
    records: list[Any] = []
    if lines:
        for line in head.splitlines()[:5]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        records = _head_records(head)
    for rec in records[:5]:
        if not isinstance(rec, dict):
            continue
        if isinstance(rec.get("messages"), list) or conversation_pair(rec):
            return True
        if ({"role", "speaker", "author", "from"} & rec.keys()) and (
            {"content", "text", "message", "body"} & rec.keys()
        ):
            return True
    return False


def _looks_like_whatsapp(path: Path) -> bool:
    """Three timestamped lines among the first 200.

    It used to want three full message lines among the first 20, and a real export failed
    that: its first line was a system notice with no sender, and its messages ran over many
    lines each, so only one of the first 20 lines carried a timestamp.
    """
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as fh:
            lines = [fh.readline() for _ in range(200)]
    except OSError:
        return False
    return sum(bool(_WHATSAPP_STAMP.match(line)) for line in lines) >= 3


def classify(path: Path) -> Source:
    """Decide the kind of one file from its extension and, where needed, its first bytes."""
    ext = path.suffix.lower()
    fmt = ext.lstrip(".") or "none"
    if ext in AUDIO_EXT:
        return Source(path, "audio", fmt)
    if ext in UNREADABLE_AUDIO_EXT:
        return Source(path, "audio", fmt, readable=False, note="convert to WAV or FLAC first")
    if ext in JSON_EXT:
        head = _head(path)
        if ext == ".json" and _is_json_lines(head):
            fmt = "jsonl"  # what the file holds, which is what decides how to read it
        if _looks_like_chat_json(head, lines=fmt in {"jsonl", "ndjson"}):
            return Source(path, "chat", fmt)
        return Source(path, "table", fmt)
    if ext in TABLE_EXT:
        delimiter = "\t" if ext == ".tsv" else ","
        if ext != ".sql" and conversation_pair(_csv_header(path, delimiter)):
            return Source(path, "chat", fmt)
        return Source(path, "table", fmt)
    if ext in BINARY_TABLE_EXT:
        return Source(path, "table", fmt, readable=False, note="export to CSV to profile")
    if ext == ".txt" and _looks_like_whatsapp(path):
        return Source(path, "chat", "whatsapp")
    if ext in DOCUMENT_EXT:
        return Source(path, "document", fmt)
    if ext in BINARY_DOCUMENT_EXT:
        return Source(path, "document", fmt, readable=False, note="text extraction not in core yet")
    return Source(path, "other", fmt, readable=False)


def discover(root: Path) -> list[Source]:
    """Every file under `root`, classified, in a stable order. Hidden files are skipped."""
    sources = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        sources.append(classify(path))
    return sources
