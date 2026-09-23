"""Walk a data folder and sort each file into a source kind."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
_WHATSAPP_LINE = re.compile(
    r"^\[?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4},? \d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]\.?m\.?)?\]?"
    r"\s?[-–]?\s?(?P<speaker>[^:]{1,60}): ",
    re.I,
)


@dataclass(frozen=True)
class Source:
    """One file and what vakforge thinks it is."""

    path: Path
    kind: Kind
    format: str
    readable: bool = True
    note: str = ""


def _looks_like_chat_json(path: Path) -> bool:
    """JSON or JSONL whose records carry role/speaker + content/text, or a `messages` list."""
    try:
        with path.open(encoding="utf-8-sig") as fh:
            head = fh.read(20_000)
    except (OSError, UnicodeDecodeError):
        return False
    records = []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        for line in head.splitlines()[:5]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        try:
            data = json.loads(head)
        except json.JSONDecodeError:
            return False
        records = data if isinstance(data, list) else [data]
    for rec in records[:5]:
        if not isinstance(rec, dict):
            continue
        if isinstance(rec.get("messages"), list):
            return True
        if ({"role", "speaker", "author", "from"} & rec.keys()) and (
            {"content", "text", "message", "body"} & rec.keys()
        ):
            return True
    return False


def _looks_like_whatsapp(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as fh:
            lines = [fh.readline() for _ in range(20)]
    except OSError:
        return False
    return sum(bool(_WHATSAPP_LINE.match(line)) for line in lines) >= 3


def classify(path: Path) -> Source:
    """Decide the kind of one file from its extension and, where needed, its first bytes."""
    ext = path.suffix.lower()
    fmt = ext.lstrip(".") or "none"
    if ext in AUDIO_EXT:
        return Source(path, "audio", fmt)
    if ext in UNREADABLE_AUDIO_EXT:
        return Source(path, "audio", fmt, readable=False, note="convert to WAV or FLAC first")
    if ext in JSON_EXT:
        if _looks_like_chat_json(path):
            return Source(path, "chat", fmt)
        return Source(path, "table", fmt)
    if ext in TABLE_EXT:
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
