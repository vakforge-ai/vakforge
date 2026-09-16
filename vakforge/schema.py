"""Canonical dataset schema (`vakforge.jsonl`). Source of truth for docs/DATA_FORMAT.md.

Structural rules that need only the record itself live here as pydantic validators.
Rules that need the filesystem or the locale registry live in `vakforge.validate`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1"

Speaker = Literal["user", "agent", "tool"]
Condition = Literal["studio", "clean", "phone", "noisy"]
Source = Literal["real", "synthetic", "public"]
Consent = Literal["recorded_verbal", "written", "synthetic", "public_license", "none"]
Split = Literal["train", "val", "test"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Audio(_Strict):
    path: str
    sample_rate: int = 24000
    channels: int = Field(ge=1, le=2)
    channel_map: dict[str, Speaker] | None = None
    duration_s: float = Field(ge=0)
    condition: Condition = "clean"

    @model_validator(mode="after")
    def _channel_map_matches(self) -> Audio:
        if self.channels == 2 and self.channel_map is None:
            raise ValueError("stereo audio needs channel_map, e.g. {'0': 'user', '1': 'agent'}")
        if self.channel_map is not None and set(self.channel_map) != {
            str(i) for i in range(self.channels)
        }:
            raise ValueError(f"channel_map keys must be {[str(i) for i in range(self.channels)]}")
        return self


class Language(_Strict):
    primary: str
    mix: list[str] = Field(default_factory=list)


class Tool(_Strict):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})


class ToolCall(_Strict):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(_Strict):
    id: str
    content: dict[str, Any] = Field(default_factory=dict)


class Entity(_Strict):
    type: str
    text: str
    start_char: int | None = None
    end_char: int | None = None
    normalized: Any = None


class Turn(_Strict):
    speaker: Speaker
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str | None = None
    lang: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    overlap: bool = False
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None

    @property
    def spoken(self) -> bool:
        return self.tool_call is None and self.tool_result is None

    @model_validator(mode="after")
    def _shape(self) -> Turn:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) < start ({self.start})")
        if self.tool_call and self.tool_result:
            raise ValueError("a turn carries either tool_call or tool_result, not both")
        if self.tool_call and self.speaker != "agent":
            raise ValueError("tool_call turns must have speaker='agent'")
        if self.tool_result and self.speaker != "tool":
            raise ValueError("tool_result turns must have speaker='tool'")
        if self.speaker == "tool" and not self.tool_result:
            raise ValueError("speaker='tool' turns must carry tool_result")
        if self.spoken:
            if not self.text:
                raise ValueError("spoken turns need non-empty text")
            if not self.lang:
                raise ValueError("spoken turns need lang (BCP-47, e.g. 'en-US', 'hi-Latn')")
        return self


class Transcription(_Strict):
    engine: str
    verified_by_human: bool = False


class Diarization(_Strict):
    engine: str
    confidence: float = Field(ge=0, le=1, default=1.0)


class Meta(_Strict):
    source: Source
    consent: Consent
    consent_ref: str | None = None
    voice_consent_ref: str | None = None
    license: str | None = None
    pii_redacted: bool
    redaction_log: str | None = None
    transcription: Transcription | None = None
    diarization: Diarization | None = None
    split: Split
    created: datetime


class Conversation(_Strict):
    """One conversation. Audio is optional: records built from documents, tables or chat
    logs have no recording until `synth` renders one."""

    id: str
    schema_version: str = SCHEMA_VERSION
    audio: Audio | None = None
    locale: str
    language: Language
    domain: str | None = None
    scenario: str | None = None
    system_prompt: str | None = None
    tools: list[Tool] = Field(default_factory=list)
    turns: list[Turn] = Field(min_length=1)
    meta: Meta

    @model_validator(mode="after")
    def _cross_turn_rules(self) -> Conversation:
        prev_start = -1.0
        for i, t in enumerate(self.turns):
            if t.start < prev_start:
                raise ValueError(f"turns[{i}]: turns must be sorted by start")
            prev_start = t.start

        tool_names = {t.name for t in self.tools}
        call_ids: set[str] = set()
        for i, t in enumerate(self.turns):
            if t.tool_call:
                if t.tool_call.id in call_ids:
                    raise ValueError(f"turns[{i}]: duplicate tool_call id {t.tool_call.id!r}")
                call_ids.add(t.tool_call.id)
                if t.tool_call.name not in tool_names:
                    raise ValueError(
                        f"turns[{i}]: tool_call {t.tool_call.name!r} not declared in tools"
                    )
            if t.tool_result and t.tool_result.id not in call_ids:
                raise ValueError(
                    f"turns[{i}]: tool_result references unknown call id {t.tool_result.id!r}"
                )

        if self.audio and self.turns:
            last_end = max(t.end for t in self.turns)
            if last_end > self.audio.duration_s + 0.5:
                raise ValueError(
                    f"turns end at {last_end}s but audio.duration_s is {self.audio.duration_s}s"
                )
        return self


def json_schema() -> dict[str, Any]:
    """JSON Schema for one `vakforge.jsonl` line, for external validators."""
    schema = Conversation.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = f"vakforge conversation v{SCHEMA_VERSION}"
    return schema
