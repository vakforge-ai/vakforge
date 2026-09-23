"""Per-source facts for `inspect`. Deliberately shallow: enough for `recommend` to decide.

Documents: words, languages, PII counts. Tables: columns, rows, id-like columns (tool
candidates). Chats: messages and speakers. Audio: duration, format, clipping, silence.

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
from pathlib import Path
from typing import Any

import numpy as np

from vakforge.inspect.sources import _WHATSAPP_LINE, Source
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
_ID_COLUMN = re.compile(r"(^id$|_id$|^id_|number$|_no$|^sku$|^email$|^phone$)", re.I)
MAX_CHARS = 2_000_000  # read at most this much text per file


class FileTooLarge(ValueError):
    """Raised for a file that only parses as a whole and is over `MAX_CHARS`.

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
    text, truncated = _read_text(path)
    if truncated:
        raise FileTooLarge(
            f"over {MAX_CHARS:,} characters and must be parsed whole; "
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


def profile_table(src: Source, pack: LocalePack) -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {}
    truncated = False
    parse_errors: list[str] = []
    if src.format in {"csv", "tsv"}:
        with src.path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t" if src.format == "tsv" else ",")
            # Counted, not collected: only the number was ever used, and a large CRM
            # export should not have to fit in memory to be counted.
            n_rows = sum(1 for _ in reader)
        tables[src.path.stem] = {"columns": reader.fieldnames or [], "rows": n_rows}
    elif src.format == "sql":
        sql, truncated = _read_text(src.path)
        for match in _CREATE_TABLE.finditer(sql):
            body = sql[match.end() : sql.find(";", match.end())]
            cols = re.findall(r"^\s*[`\"\[]?(\w+)[`\"\]]?\s+\w+", body, re.M)
            tables[match.group(1)] = {"columns": cols, "rows": None}
    elif src.format == "json":
        data = json.loads(_whole_text(src.path))
        rows = (
            data
            if isinstance(data, list)
            else next((v for v in data.values() if isinstance(v, list)), [data])
        )
        rows = [r for r in rows if isinstance(r, dict)]
        tables[src.path.stem] = {"columns": _columns_from_rows(rows), "rows": len(rows)}
    else:  # jsonl / ndjson records
        text, truncated = _read_text(src.path)
        records, parse_errors = _jsonl_rows(text, truncated)
        rows = [r for r in records if isinstance(r, dict)]
        tables[src.path.stem] = {"columns": _columns_from_rows(rows), "rows": len(rows)}
    for name, t in tables.items():
        t["id_columns"] = [c for c in t["columns"] if _ID_COLUMN.search(c)]
        t["tool_candidates"] = [f"lookup_{name}_by_{c}" for c in t["id_columns"][:3]]
    facts: dict[str, Any] = {"tables": tables}
    if truncated:
        facts["truncated"] = True  # row counts cover the part we read, not the whole file
    if parse_errors:
        facts["parse_errors"] = parse_errors  # counted rows exclude these
    return facts


def profile_chat(src: Source, pack: LocalePack) -> dict[str, Any]:
    speakers: Counter[str] = Counter()
    messages: list[str] = []
    truncated = False
    if src.format == "whatsapp":
        text, truncated = _read_text(src.path)
        for line in text.splitlines():
            if m := _WHATSAPP_LINE.match(line):
                speaker = m.group("speaker").strip()
                speakers[speaker] += 1
                messages.append(line[m.end() :])
            elif messages:
                # A message that wrapped onto its own line carries no timestamp header; it
                # belongs to the message above, and dropping it loses most long messages.
                messages[-1] += "\n" + line
    else:
        records: list[Any] = []
        if src.format == "json":
            data = json.loads(_whole_text(src.path))
            records += data if isinstance(data, list) else [data]
        else:
            text, truncated = _read_text(src.path)
            for row in _jsonl_rows(text, truncated):
                records += row if isinstance(row, list) else [row]
        for rec in records:
            turns = rec.get("messages", [rec]) if isinstance(rec, dict) else []
            for turn in turns:
                who = next(
                    (turn[k] for k in ("role", "speaker", "author", "from") if k in turn), "?"
                )
                body = next(
                    (turn[k] for k in ("content", "text", "message", "body") if k in turn), ""
                )
                speakers[str(who)] += 1
                messages.append(str(body))
    facts = _text_facts("\n\n".join(messages), pack)
    facts.update(messages=len(messages), speakers=dict(speakers.most_common(10)))
    if truncated:
        facts["truncated"] = True  # message count covers the part we read
    return facts


def profile_audio(src: Source, pack: LocalePack) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(str(src.path))
    data, sr = sf.read(str(src.path), dtype="float32", always_2d=True, frames=sr_cap(info))
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
    return {
        "duration_s": round(info.duration, 2),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        # True for telephone-band audio, which limits which models can be trained on it.
        "narrowband": info.samplerate <= 8000,
        "clipping_ratio": round(clipping, 5),
        "silence_ratio": round(silence, 3),
    }


def sr_cap(info: Any) -> int:
    """Read at most 10 minutes per file; stats on the head are representative enough."""
    return min(info.frames, info.samplerate * 600)


PROFILERS = {
    "document": profile_document,
    "table": profile_table,
    "chat": profile_chat,
    "audio": profile_audio,
}
