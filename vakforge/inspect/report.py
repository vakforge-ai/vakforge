"""Assemble per-file facts into one report and `inspect.json`."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vakforge.inspect.profile import PROFILERS, FileTooLarge
from vakforge.inspect.sources import discover
from vakforge.locales.base import LocalePack

REPORT_VERSION = "0.1"
# Errors one bad file may raise; any other exception is a bug and should surface.
FILE_ERRORS = (OSError, ValueError, UnicodeError, RuntimeError, csv.Error, KeyError, TypeError)


def inspect_dir(
    root: Path, pack: LocalePack, on_file: Callable[[int, int, str], None] | None = None
) -> dict[str, Any]:
    """Profile every file under `root` with `pack` and summarise the whole folder.

    `on_file(done, total, path)` is called before each file is read, so a caller can show
    progress; a large export can take a while, and silence reads as a hang.
    """
    files: list[dict[str, Any]] = []
    sources = discover(root)
    for done, src in enumerate(sources):
        if on_file:
            on_file(done, len(sources), src.path.relative_to(root).as_posix())
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
                # Our own limits explain themselves; any other error keeps its type, which is
                # the useful half of, say, "UnicodeDecodeError: ...".
                entry["error"] = (
                    str(exc) if isinstance(exc, FileTooLarge) else f"{type(exc).__name__}: {exc}"
                )
        files.append(entry)
    return {
        "report_version": REPORT_VERSION,
        "root": root.as_posix(),  # same spelling on every OS, so reports diff cleanly
        "locale": pack.id,
        "summary": summarise(files),
        "files": files,
    }


KINDS = ("document", "table", "chat", "audio", "other")


def summarise(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Totals for the folder.

    `counts` is what was found, `profiled` is what yielded facts. Every other total below
    is built only from profiled files, so the two counts together say how much of the
    folder the numbers actually cover.
    """
    kinds = Counter(f["kind"] for f in files)
    profiled_kinds = Counter(f["kind"] for f in files if "facts" in f)
    languages: Counter[str] = Counter()
    pii: Counter[str] = Counter()
    tool_candidates: list[str] = []
    words = messages = two_channel = truncated = 0
    audio_seconds = 0.0
    for f in files:
        facts = f.get("facts", {})
        languages.update(facts.get("languages", {}))
        pii.update(facts.get("pii", {}))
        truncated += bool(facts.get("truncated"))
        if f["kind"] == "document":
            words += facts.get("words", 0)
        if f["kind"] == "chat":
            messages += facts.get("messages", 0)
        if f["kind"] == "audio":
            audio_seconds += facts.get("duration_s", 0.0)
            two_channel += facts.get("channels", 0) == 2
        for table in facts.get("tables", {}).values():
            tool_candidates += table.get("tool_candidates", [])
    return {
        "counts": {k: kinds.get(k, 0) for k in KINDS},
        "profiled": {k: profiled_kinds.get(k, 0) for k in KINDS},
        "unreadable": sum(not f["readable"] for f in files),
        "truncated": truncated,
        "document_words": words,
        "chat_messages": messages,
        "audio_hours": round(audio_seconds / 3600, 4),
        "two_channel_audio_files": two_channel,
        "languages": dict(languages.most_common()),
        "pii": dict(pii.most_common()),
        "tool_candidates": list(dict.fromkeys(tool_candidates)),
    }


def is_sampled(report: dict[str, Any]) -> bool:
    """True when a large table or conversation export was scanned from a sample, so its
    personal-data and language counts are not totals and should not be read as such."""
    return any(
        t["rows_scanned"] < t["rows"]
        for f in report["files"]
        for t in f.get("facts", {}).get("tables", {}).values()
        if "rows_scanned" in t
    ) or any("messages_scanned" in f.get("facts", {}) for f in report["files"])


def write_report(report: dict[str, Any], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
