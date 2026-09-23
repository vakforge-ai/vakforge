"""Shared fixtures. Audio is generated in code; nothing binary is committed."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Rich wraps and truncates to the terminal width, so CLI output depends on where the
# suite runs: a long `/tmp/pytest-of-runner/...` path on CI split a phrase across lines
# that stayed on one line under a short Windows temp dir, and the assertion failed there
# and nowhere else. Pin the width so output is the same everywhere.
os.environ["COLUMNS"] = "200"

import numpy as np
import pytest
import soundfile as sf

SR = 24000


def write_wav(path: Path, seconds: float = 2.0, channels: int = 1, sr: int = SR) -> Path:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False, dtype=np.float32)
    mono = 0.2 * np.sin(2 * np.pi * 440 * t)
    data = mono if channels == 1 else np.stack([mono, 0.2 * np.sin(2 * np.pi * 660 * t)], axis=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), data, sr, subtype="FLOAT")
    return path


def conversation(**overrides) -> dict:
    """A valid canonical record. Override any top-level key."""
    base = {
        "id": "conv_0001",
        "schema_version": "0.1",
        "audio": {
            "path": "audio/conv_0001.wav",
            "sample_rate": SR,
            "channels": 2,
            "channel_map": {"0": "user", "1": "agent"},
            "duration_s": 2.0,
            "condition": "phone",
        },
        "locale": "en-US",
        "language": {"primary": "en-US", "mix": ["en-US"]},
        "domain": "support",
        "scenario": "book_visit",
        "system_prompt": "You are Sam from Acme support.",
        "tools": [
            {
                "name": "book_appointment",
                "description": "Book a visit",
                "parameters": {
                    "type": "object",
                    "properties": {"customer_id": {"type": "string"}},
                    "required": ["customer_id"],
                },
            }
        ],
        "turns": [
            {"speaker": "agent", "start": 0.0, "end": 0.8, "text": "Hi, Acme.", "lang": "en-US"},
            {
                "speaker": "user",
                "start": 0.9,
                "end": 1.5,
                "text": "Book me, ID A-1.",
                "lang": "en-US",
                "entities": [{"type": "customer_id", "text": "A-1"}],
            },
            {
                "speaker": "agent",
                "start": 1.5,
                "end": 1.5,
                "tool_call": {
                    "id": "c1",
                    "name": "book_appointment",
                    "arguments": {"customer_id": "A-1"},
                },
            },
            {
                "speaker": "tool",
                "start": 1.5,
                "end": 1.5,
                "tool_result": {"id": "c1", "content": {"ok": True}},
            },
            {"speaker": "agent", "start": 1.6, "end": 2.0, "text": "Done.", "lang": "en-US"},
        ],
        "meta": {
            "source": "synthetic",
            "consent": "synthetic",
            "pii_redacted": True,
            "split": "train",
            "created": "2026-09-16T10:12:00Z",
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def valid_conv() -> dict:
    return conversation()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A data dir with one stereo WAV and a valid one-row manifest."""
    write_wav(tmp_path / "audio" / "conv_0001.wav", channels=2)
    manifest = tmp_path / "vakforge.jsonl"
    manifest.write_text(json.dumps(conversation()) + "\n", encoding="utf-8")
    return tmp_path
