"""`vakforge validate`: file-level rules from docs/DATA_FORMAT.md.

Schema-only rules are enforced by `vakforge.schema`; this module adds the checks that need
the filesystem (audio files), the locale registry, JSON-Schema tool arguments, and splits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import jsonschema
from pydantic import ValidationError

from vakforge.locales import get_pack
from vakforge.locales.base import LocalePack
from vakforge.schema import Conversation, RedactionLog


@dataclass(frozen=True)
class Issue:
    conv_id: str
    field: str
    message: str
    fix: str = ""
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line} " if self.line else ""
        s = f"{where}{self.conv_id} · {self.field}: {self.message}"
        return f"{s}  → {self.fix}" if self.fix else s


def _pydantic_issues(conv_id: str, line: int, err: ValidationError) -> list[Issue]:
    out = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "<record>"
        msg = e["msg"].removeprefix("Value error, ")
        out.append(Issue(conv_id, loc, msg, line=line))
    return out


def _check_audio(conv: Conversation, root: Path, line: int) -> list[Issue]:
    if conv.audio is None:
        return []
    import soundfile as sf  # local import keeps `import vakforge.schema` light

    path = root / conv.audio.path
    if not path.exists():
        return [Issue(conv.id, "audio.path", f"{path} does not exist", "fix the path", line)]
    try:
        info = sf.info(str(path))
    except Exception as exc:  # soundfile raises RuntimeError/LibsndfileError
        return [Issue(conv.id, "audio.path", f"cannot decode: {exc}", "re-encode as WAV", line)]
    issues = []
    if info.samplerate != conv.audio.sample_rate:
        issues.append(
            Issue(
                conv.id,
                "audio.sample_rate",
                f"declared {conv.audio.sample_rate}, file is {info.samplerate}",
                "run `vakforge prepare` to resample or fix the declaration",
                line,
            )
        )
    if info.channels != conv.audio.channels:
        issues.append(
            Issue(
                conv.id,
                "audio.channels",
                f"declared {conv.audio.channels}, file has {info.channels}",
                "fix the declaration or channel_map",
                line,
            )
        )
    if abs(info.duration - conv.audio.duration_s) > 0.5:
        issues.append(
            Issue(
                conv.id,
                "audio.duration_s",
                f"declared {conv.audio.duration_s}, file is {info.duration:.2f}",
                "set duration_s from the file",
                line,
            )
        )
    return issues


def _check_locale(conv: Conversation, line: int) -> list[Issue]:
    try:
        pack = get_pack(conv.locale)
    except KeyError as exc:
        return [Issue(conv.id, "locale", str(exc), "use a registered pack id", line)]
    allowed = pack.all_languages()
    fix = "tag the turn with a language the pack declares, or pick another locale"
    issues = []
    for i, t in enumerate(conv.turns):
        # Both fields name languages, so both are held to the pack's list.
        tags = [("lang", t.lang)] if t.lang else []
        tags += [("lang_mix", tag) for tag in t.lang_mix]
        for field, tag in tags:
            if tag not in allowed:
                issues.append(
                    Issue(
                        conv.id,
                        f"turns[{i}].{field}",
                        f"{tag!r} is not declared by pack {conv.locale!r} "
                        f"(allowed: {sorted(allowed)})",
                        fix,
                        line,
                    )
                )
    return issues


def _check_tools(conv: Conversation, line: int) -> list[Issue]:
    issues = []
    schemas = {}
    for i, tool in enumerate(conv.tools):
        try:
            jsonschema.Draft202012Validator.check_schema(tool.parameters)
            schemas[tool.name] = jsonschema.Draft202012Validator(tool.parameters)
        except jsonschema.SchemaError as exc:
            issues.append(
                Issue(
                    conv.id,
                    f"tools[{i}].parameters",
                    f"invalid JSON Schema: {exc.message}",
                    "fix the parameters schema",
                    line,
                )
            )
    for i, t in enumerate(conv.turns):
        if t.tool_call and (v := schemas.get(t.tool_call.name)):
            for err in v.iter_errors(t.tool_call.arguments):
                issues.append(
                    Issue(
                        conv.id,
                        f"turns[{i}].tool_call.arguments",
                        err.message,
                        "make the arguments match tools[].parameters",
                        line,
                    )
                )
    return issues


def _redactable_text(conv: Conversation) -> list[tuple[str, str]]:
    """Every (field path, text) a `pii_redacted` claim covers.

    Tool arguments and results are included: a customer's number is just as exposed sitting
    in `arguments` as it is in a spoken turn, and the row is trained on either way.
    """
    out: list[tuple[str, str]] = []
    if conv.system_prompt:
        out.append(("system_prompt", conv.system_prompt))
    for i, t in enumerate(conv.turns):
        if t.text:
            out.append((f"turns[{i}].text", t.text))
        if t.tool_call:
            args = json.dumps(t.tool_call.arguments, ensure_ascii=False)
            out.append((f"turns[{i}].tool_call.arguments", args))
        if t.tool_result:
            content = json.dumps(t.tool_result.content, ensure_ascii=False)
            out.append((f"turns[{i}].tool_result.content", content))
    return out


def _check_redaction(conv: Conversation, pack: LocalePack, root: Path, line: int) -> list[Issue]:
    """`pii_redacted: true` is a claim about the data, so prove it instead of trusting it.

    The schema can only check that the flag and the log reference are present. Here we
    re-run the locale pack over the text that is actually in the record: if anything the
    pack recognises survives, the claim is false and the row must not be trained on.

    Matched text is never repeated in the issue — reporting a leak should not copy the
    personal data into a terminal, a CI log or a bug report.
    """
    if not conv.meta.pii_redacted:
        return []
    issues: list[Issue] = []

    if conv.meta.redaction_log:
        issues += _check_redaction_log(conv, root, line)

    for field, text in _redactable_text(conv):
        for span in pack.find_pii(text):
            issues.append(
                Issue(
                    conv.id,
                    field,
                    f"pii_redacted is true, but {span.type} is still present "
                    f"at characters {span.start}-{span.end}",
                    "redact it before writing the row, or set pii_redacted=false",
                    line,
                )
            )
    return issues


def _inside(root: Path, target: Path) -> bool:
    """Is `target` really under `root` once both are fully resolved?

    The schema already rejects an absolute path or a `..` segment in the declared string.
    This is the second layer, and it catches what a string check cannot: a symlink inside
    the dataset pointing anywhere on the machine.
    """
    try:
        return target.resolve().is_relative_to(root.resolve())
    except OSError:  # a broken link or a path we cannot stat is not inside
        return False


def _check_redaction_log(conv: Conversation, root: Path, line: int) -> list[Issue]:
    """The log has to exist inside the dataset, parse, and describe *this* record.

    An empty `spans` list is accepted: a conversation may genuinely contain no personal
    data. The substantive proof is the rescan in `_check_redaction`, which reads the text
    itself — this only establishes that the log is coherent and belongs to this row, so a
    log copied from another conversation cannot stand in as evidence.
    """
    issue = partial(Issue, conv.id, "meta.redaction_log", line=line)
    path = root / conv.meta.redaction_log
    if not _inside(root, path):
        return [
            issue(
                "resolves outside the dataset directory",
                "keep the log beside the manifest; a path that leaves the dataset is not "
                "evidence about it",
            )
        ]
    if not path.exists():
        return [issue(f"{conv.meta.redaction_log} does not exist", "point at the real log")]
    try:
        log = RedactionLog.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        first = str(exc).splitlines()[0]
        return [issue(f"unreadable or malformed: {first}", "see docs/DATA_FORMAT.md")]

    issues = []
    if log.conversation_id and log.conversation_id != conv.id:
        issues.append(
            issue(
                f"names conversation {log.conversation_id!r}, not this one",
                "a log from another conversation is not evidence about this one",
            )
        )
    for n, span in enumerate(log.spans):
        if span.turn is None:
            continue
        if not 0 <= span.turn < len(conv.turns):
            issues.append(issue(f"spans[{n}] points at turn {span.turn}, which does not exist"))
            continue
        # The placeholder is what should be left behind where the data was removed. If it
        # is not there, the log is describing a redaction that did not happen.
        text = conv.turns[span.turn].text or ""
        if span.placeholder and span.placeholder not in text:
            issues.append(
                issue(
                    f"spans[{n}] claims placeholder {span.placeholder!r} in turn "
                    f"{span.turn}, which does not contain it",
                    "write the log from the redaction that actually ran",
                )
            )
    return issues


def _check_consent(conv: Conversation, line: int, allow_unconsented: bool) -> list[Issue]:
    if conv.meta.consent == "none" and not allow_unconsented:
        return [
            Issue(
                conv.id,
                "meta.consent",
                "consent is 'none'",
                "record a consent basis, or pass --allow-unconsented (row stays unexportable)",
                line,
            )
        ]
    return []


def _check_splits(convs: list[Conversation], root: Path) -> list[Issue]:
    """`splits.json`, when present, must agree with meta.split and cover every id."""
    path = root / "splits.json"
    if not path.exists():
        return []
    try:
        splits: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [Issue("<splits.json>", "splits.json", f"invalid JSON: {exc}", "fix the file")]
    assigned: dict[str, str] = {}
    issues = []
    for split, ids in splits.items():
        if split == "seed":
            continue
        for cid in ids:
            if cid in assigned:
                issues.append(
                    Issue(cid, "splits.json", f"in both {assigned[cid]} and {split}", "keep one")
                )
            assigned[cid] = split
    for c in convs:
        if c.id not in assigned:
            issues.append(Issue(c.id, "splits.json", "not assigned to any split", "add it"))
        elif assigned[c.id] != c.meta.split:
            issues.append(
                Issue(
                    c.id,
                    "meta.split",
                    f"row says {c.meta.split!r}, splits.json says {assigned[c.id]!r}",
                    "make them agree",
                )
            )
    return issues


def validate_manifest(
    manifest: Path, *, allow_unconsented: bool = False
) -> tuple[list[Conversation], list[Issue]]:
    """Validate a `vakforge.jsonl`. Returns the parsed conversations and every issue found.

    Audio paths resolve relative to the manifest's directory, per docs/DATA_FORMAT.md.
    """
    root = manifest.parent
    convs: list[Conversation] = []
    issues: list[Issue] = []
    seen_ids: set[str] = set()

    with manifest.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                issues.append(Issue("<unparsed>", "json", str(exc), "fix the JSON", line_no))
                continue
            conv_id = str(data.get("id", "<no id>")) if isinstance(data, dict) else "<no id>"
            try:
                conv = Conversation.model_validate(data)
            except ValidationError as exc:
                issues.extend(_pydantic_issues(conv_id, line_no, exc))
                continue
            if conv.id in seen_ids:
                issues.append(Issue(conv.id, "id", "duplicate id", "ids must be unique", line_no))
            seen_ids.add(conv.id)
            convs.append(conv)
            issues += _check_audio(conv, root, line_no)
            issues += _check_locale(conv, line_no)
            issues += _check_tools(conv, line_no)
            issues += _check_consent(conv, line_no, allow_unconsented)
            try:  # an unknown pack is already reported by _check_locale
                pack = get_pack(conv.locale)
            except KeyError:
                pass
            else:
                issues += _check_redaction(conv, pack, root, line_no)

    issues += _check_splits(convs, root)
    return convs, issues
