"""Assemble per-file facts into one report and `inspect.json`."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from vakforge.inspect.profile import PROFILERS
from vakforge.inspect.sources import discover
from vakforge.locales.base import LocalePack

REPORT_VERSION = "0.1"
# Errors one bad file may raise; any other exception is a bug and should surface.
FILE_ERRORS = (OSError, ValueError, UnicodeError, RuntimeError, csv.Error, KeyError, TypeError)


def inspect_dir(root: Path, pack: LocalePack) -> dict[str, Any]:
    """Profile every file under `root` with `pack` and summarise the whole folder."""
    files: list[dict[str, Any]] = []
    for src in discover(root):
        entry: dict[str, Any] = {
            "path": src.path.relative_to(root).as_posix(),
            "kind": src.kind,
            "format": src.format,
            "readable": src.readable,
        }
        if src.note:
            entry["note"] = src.note
        if src.readable and src.kind in PROFILERS:
            try:
                entry["facts"] = PROFILERS[src.kind](src, pack)
            except FILE_ERRORS as exc:
                entry["readable"] = False
                entry["error"] = f"{type(exc).__name__}: {exc}"
        files.append(entry)
    return {
        "report_version": REPORT_VERSION,
        "root": str(root),
        "locale": pack.id,
        "summary": summarise(files),
        "files": files,
    }


def summarise(files: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = Counter(f["kind"] for f in files)
    languages: Counter[str] = Counter()
    pii: Counter[str] = Counter()
    tool_candidates: list[str] = []
    words = messages = stereo = 0
    audio_seconds = 0.0
    for f in files:
        facts = f.get("facts", {})
        languages.update(facts.get("languages", {}))
        pii.update(facts.get("pii", {}))
        if f["kind"] == "document":
            words += facts.get("words", 0)
        if f["kind"] == "chat":
            messages += facts.get("messages", 0)
        if f["kind"] == "audio":
            audio_seconds += facts.get("duration_s", 0.0)
            stereo += bool(facts.get("stereo_split_possible"))
        for table in facts.get("tables", {}).values():
            tool_candidates += table.get("tool_candidates", [])
    return {
        "counts": {k: kinds.get(k, 0) for k in ("document", "table", "chat", "audio", "other")},
        "unreadable": sum(not f["readable"] for f in files),
        "document_words": words,
        "chat_messages": messages,
        "audio_hours": round(audio_seconds / 3600, 2),
        "stereo_audio_files": stereo,
        "languages": dict(languages.most_common()),
        "pii": dict(pii.most_common()),
        "tool_candidates": list(dict.fromkeys(tool_candidates)),
    }


def write_report(report: dict[str, Any], out: Path) -> Path:
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
