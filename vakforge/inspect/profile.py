"""Per-source facts for `inspect`. Deliberately shallow: enough for `recommend` to decide.

Documents: words, languages, PII counts. Tables: columns, rows, id-like columns (tool
candidates). Chats: messages and speakers. Audio: duration, format, clipping, silence.
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
_CREATE_TABLE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"\[]?(\w+)", re.I)
_ID_COLUMN = re.compile(r"(^id$|_id$|^id_|number$|_no$|^sku$|^email$|^phone$)", re.I)
MAX_BYTES = 2_000_000  # read at most this much text per file


def _read_text(path: Path) -> str:
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        return fh.read(MAX_BYTES)


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
    text = _read_text(src.path)
    if src.format in {"html", "htm"}:
        text = _TAG.sub(" ", text)
    return _text_facts(text, pack)


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    cols: dict[str, None] = {}
    for row in rows[:50]:
        cols.update(dict.fromkeys(row))
    return list(cols)


def profile_table(src: Source, pack: LocalePack) -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {}
    if src.format in {"csv", "tsv"}:
        with src.path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t" if src.format == "tsv" else ",")
            rows = list(reader)
        tables[src.path.stem] = {"columns": reader.fieldnames or [], "rows": len(rows)}
    elif src.format == "sql":
        sql = _read_text(src.path)
        for match in _CREATE_TABLE.finditer(sql):
            body = sql[match.end() : sql.find(";", match.end())]
            cols = re.findall(r"^\s*[`\"\[]?(\w+)[`\"\]]?\s+\w+", body, re.M)
            tables[match.group(1)] = {"columns": cols, "rows": None}
    else:  # json / jsonl records
        text = _read_text(src.path)
        if src.format == "json":
            data = json.loads(text)
            rows = (
                data
                if isinstance(data, list)
                else next((v for v in data.values() if isinstance(v, list)), [data])
            )
        else:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        rows = [r for r in rows if isinstance(r, dict)]
        tables[src.path.stem] = {"columns": _columns_from_rows(rows), "rows": len(rows)}
    for name, t in tables.items():
        t["id_columns"] = [c for c in t["columns"] if _ID_COLUMN.search(c)]
        t["tool_candidates"] = [f"lookup_{name}_by_{c}" for c in t["id_columns"][:3]]
    return {"tables": tables}


def profile_chat(src: Source, pack: LocalePack) -> dict[str, Any]:
    text = _read_text(src.path)
    speakers: Counter[str] = Counter()
    messages: list[str] = []
    if src.format == "whatsapp":
        for line in text.splitlines():
            if m := _WHATSAPP_LINE.match(line):
                speaker = re.split(r"\s[-–]\s", m.group(0))[-1].rstrip(": ").strip()
                speakers[speaker] += 1
                messages.append(line[m.end() :])
    else:
        lines = [text] if src.format == "json" else text.splitlines()
        records: list[Any] = []
        for line in lines:
            if line.strip():
                data = json.loads(line)
                records += data if isinstance(data, list) else [data]
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
    condition = "phone" if sr <= 8000 else "noisy" if silence < 0.05 else "clean"
    return {
        "duration_s": round(info.duration, 2),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "stereo_split_possible": info.channels == 2,
        "clipping_ratio": round(clipping, 5),
        "silence_ratio": round(silence, 3),
        "condition_guess": condition,
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
