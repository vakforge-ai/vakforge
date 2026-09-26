"""vakforge CLI. Thin: each subcommand delegates to a module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, TextIO

import typer
from rich.console import Console

from vakforge import GLOSSARY_URL, __version__


def make_stream_safe(stream: TextIO) -> None:
    """Replace unencodable characters instead of crashing.

    Legacy Windows consoles default to cp1252, which cannot encode characters vakforge
    prints (₹, ✗, Devanagari). Output degrades to "?" there; UTF-8 terminals are unaffected.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    if reconfigure and encoding != "utf8":
        reconfigure(errors="replace")


make_stream_safe(sys.stdout)
make_stream_safe(sys.stderr)

app = typer.Typer(
    help="Turn the data your company already has into a self-hosted voice assistant.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()
err_console = Console(stderr=True)

PROJECT_GITIGNORE = """# written by `vakforge init`
data/raw/
runs/
.venv/
*.wav
*.mp3
*.flac
*.safetensors
*.bin
*.pt
*.gguf
"""


def _version(value: bool) -> None:
    if value:
        console.print(f"vakforge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    """vakforge."""


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Project directory to create.")],
    locale: Annotated[
        list[str], typer.Option("--locale", "-l", help="Locale pack id(s), e.g. en-US.")
    ],
) -> None:
    """Scaffold a project folder with a locale."""
    from vakforge.config import ProjectConfig
    from vakforge.locales import get_pack, list_packs

    for pack_id in locale:
        try:
            get_pack(pack_id)
        except KeyError:
            err_console.print(f"[red]unknown locale {pack_id!r}[/]; known: {list_packs()}")
            raise typer.Exit(2) from None

    project = Path(name)
    if project.exists() and any(project.iterdir()):
        err_console.print(f"[red]{project} exists and is not empty[/]")
        raise typer.Exit(2)
    for sub in ("data/raw", "data/audio", "configs", "runs"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    (project / ".gitignore").write_text(PROJECT_GITIGNORE, encoding="utf-8")
    cfg_path = ProjectConfig(name=project.name, locales=locale).save(project)
    console.print(f"[green]created[/] {project}/  ({cfg_path.name}: locales={locale})")
    console.print(
        "next: drop your documents, tables, chats or audio into data/raw/ and run "
        f"`vakforge inspect {project}/data/raw`"
    )


@app.command()
def validate(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    allow_unconsented: Annotated[
        bool, typer.Option(help="Accept rows with meta.consent='none' (never exported).")
    ] = False,
) -> None:
    """Validate a canonical `vakforge.jsonl` manifest."""
    from vakforge.validate import validate_manifest

    convs, issues = validate_manifest(manifest, allow_unconsented=allow_unconsented)
    if allow_unconsented and any(c.meta.consent == "none" for c in convs):
        err_console.print(
            "[yellow]warning:[/] unconsented rows accepted; they will never be exported"
        )
    for issue in issues:
        err_console.print(f"[red]✗[/] {issue}")
    n_ok = len(convs) - len({i.conv_id for i in issues})
    console.print(f"{len(convs)} conversation(s) parsed, {n_ok} clean, {len(issues)} issue(s)")
    raise typer.Exit(1 if issues else 0)


@app.command()
def schema(
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write JSON Schema here instead of stdout.")
    ] = None,
) -> None:
    """Export the canonical JSON Schema."""
    from vakforge.schema import json_schema

    text = json.dumps(json_schema(), indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        console.print(f"[green]wrote[/] {out}")
    else:
        print(text)


def _project_locale(start: Path) -> str | None:
    """First locale in the nearest `vakforge.yaml` at or above `start`."""
    import yaml
    from pydantic import ValidationError

    from vakforge.config import CONFIG_NAME, ProjectConfig

    for folder in [start, *start.parents]:
        if (folder / CONFIG_NAME).exists():
            # A hand-edited project file used to end in a pydantic traceback.
            try:
                return ProjectConfig.load(folder).locales[0]
            except ValidationError as exc:
                first = exc.errors()[0]
                why = f"{'.'.join(str(p) for p in first['loc']) or '<file>'}: {first['msg']}"
            except (yaml.YAMLError, OSError) as exc:
                why = str(exc).splitlines()[0]
            err_console.print(f"[red]{folder / CONFIG_NAME} is not a valid project file[/]: {why}")
            raise typer.Exit(2)
    return None


def _read_json_object(path: Path, expect: str) -> dict[str, Any]:
    """`path` parsed as a JSON object, or a clean error saying it should be `expect`.

    Valid JSON is not necessarily an object: `[]`, `null` or `42` used to reach
    `report.get(...)` and die with an AttributeError.
    """
    from vakforge.validate import json_kind

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        err_console.print(f"[red]cannot read {path}[/]: {exc}")
        raise typer.Exit(2) from None
    if not isinstance(data, dict):
        err_console.print(
            f"[red]{path} holds JSON {json_kind(data)}, not an object[/]; is it {expect}?"
        )
        raise typer.Exit(2)
    return data


def _inspect_with_progress(path: Path, pack: Any) -> dict[str, Any]:
    """`inspect_dir`, with a progress bar on an interactive terminal.

    A 600 MB export takes around 20 s, and a folder of them longer; with nothing on screen
    that reads as a hang. The bar goes to stderr, only on a terminal, and clears when done,
    so piped output and CI logs are unchanged.
    """
    from vakforge.inspect.report import inspect_dir

    if not err_console.is_terminal:
        return inspect_dir(path, pack)
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    columns = (
        SpinnerColumn(),
        TextColumn("[dim]inspecting[/]"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TextColumn("{task.description}"),
    )
    with Progress(*columns, console=err_console, transient=True) as progress:
        task = progress.add_task("", total=None)

        def on_file(done: int, total: int, name: str) -> None:
            progress.update(task, total=total, completed=done, description=name)

        return inspect_dir(path, pack, on_file=on_file)


@app.command()
def inspect(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Data folder.")],
    locale: Annotated[
        str | None,
        typer.Option("--locale", "-l", help="Locale pack; defaults to the project's first."),
    ] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the report.")] = Path(
        "inspect.json"
    ),
) -> None:
    """Report what is in a folder of documents, tables, chats and audio."""
    from rich.table import Table

    from vakforge.inspect.report import is_sampled, write_report
    from vakforge.locales import get_pack, list_packs
    from vakforge.recommend.rules import fmt_kinds

    pack_id = locale or _project_locale(path.resolve())
    if pack_id is None:
        err_console.print(
            "[red]no locale[/]: pass --locale (one of "
            f"{', '.join(list_packs())}) or run inside a `vakforge init` project"
        )
        raise typer.Exit(2)
    try:
        pack = get_pack(pack_id)
    except KeyError as exc:
        err_console.print(f"[red]{exc.args[0]}[/]")
        raise typer.Exit(2) from None

    report = _inspect_with_progress(path, pack)
    s = report["summary"]
    table = Table(title=f"{path} · locale {pack.id}", title_justify="left", show_header=False)
    table.add_column(style="dim")
    table.add_column()
    counts = fmt_kinds(s["counts"])
    found = sum(s["counts"].values())
    profiled = sum(s["profiled"].values())
    table.add_row("files", counts or "none")
    # Every total below is built from the profiled files only, so show how many that is.
    table.add_row("profiled", f"{profiled} of {found}")
    table.add_row("documents", f"{s['document_words']} words")
    table.add_row("chats", f"{s['chat_messages']} messages")
    hours = s["audio_hours"]
    length = f"{hours} h" if hours >= 1 else f"{round(hours * 60, 1)} min"
    table.add_row("audio", f"{length}, {s['two_channel_audio_files']} two-channel file(s)")
    table.add_row("languages", ", ".join(f"{k} {v}" for k, v in s["languages"].items()) or "-")
    pii = ", ".join(f"{k} {v}" for k, v in s["pii"].items()) or "none found"
    table.add_row("personal data", pii + (" (large files sampled)" if is_sampled(report) else ""))
    table.add_row("tool candidates", ", ".join(s["tool_candidates"][:6]) or "-")
    console.print(table)
    for f in report["files"]:
        if not f["readable"]:
            reason = f.get("error") or f.get("note") or "unsupported type"
            err_console.print(f"[yellow]skipped[/] {f['path']}: {reason}")
        elif f.get("facts", {}).get("truncated"):
            err_console.print(
                f"[yellow]partial[/] {f['path']}: too large to read whole, counts cover the start"
            )
    write_report(report, out)
    console.print(f"[green]wrote[/] {out}")


@app.command()
def recommend(
    source: Annotated[
        Path, typer.Argument(exists=True, help="inspect.json, or a data folder to inspect first.")
    ],
    goal: Annotated[
        list[str] | None,
        typer.Option(
            "--goal",
            "-g",
            help="What should improve: knowledge, tools, workflow, recognition, voice, duplex, "
            "language. Repeatable; inferred from the data if omitted.",
        ),
    ] = None,
    gpu: Annotated[
        str, typer.Option("--gpu", help="Largest GPU you can train on: none, 24, 48 or 80 (GB).")
    ] = "none",
    duplex: Annotated[
        bool, typer.Option("--duplex", help="Callers must be able to interrupt (sub-300 ms).")
    ] = False,
    locale: Annotated[
        str | None,
        typer.Option("--locale", "-l", help="Locale pack; defaults to the project's first."),
    ] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the decision.")] = Path(
        "recommend.json"
    ),
) -> None:
    """Decide what needs changing (retrieval, tools, locale pack, fine-tune) and the recipe."""
    from pydantic import ValidationError
    from rich.table import Table

    from vakforge.locales import get_pack, list_packs
    from vakforge.recommend import Constraints
    from vakforge.recommend import recommend as decide
    from vakforge.recommend.rules import GOALS, GPU_GB, VERDICT_LABELS, fmt_number

    bad = [g for g in goal or [] if g not in GOALS]
    if bad:
        err_console.print(f"[red]unknown goal {bad[0]!r}[/]; choose from {', '.join(GOALS)}")
        raise typer.Exit(2)
    if gpu not in GPU_GB:
        err_console.print(f"[red]--gpu must be one of {', '.join(GPU_GB)}[/]")
        raise typer.Exit(2)

    def resolve_pack(pack_id: str | None, missing: str):
        """The same locale error whichever way the summary was obtained.

        Directory mode used to skip this and let the KeyError become a traceback, so the
        same bad `--locale` printed a clean message one way and a stack trace the other.
        """
        if pack_id is None:
            err_console.print(f"[red]no locale[/]: {missing}")
            raise typer.Exit(2)
        try:
            return get_pack(pack_id)
        except KeyError:
            err_console.print(f"[red]unknown locale {pack_id!r}[/]; known: {list_packs()}")
            raise typer.Exit(2) from None

    if source.is_dir():
        pack = resolve_pack(
            locale or _project_locale(source.resolve()),
            "pass --locale or run inside a `vakforge init` project",
        )
        summary = _inspect_with_progress(source, pack)["summary"]
    else:
        from vakforge.validate import json_kind

        report = _read_json_object(source, "an inspect.json")
        # A list or object here used to reach the pack lookup and die unhashable.
        report_locale = report.get("locale")
        if not isinstance(report_locale, str | None):
            err_console.print(
                f"[red]{source}: locale[/]: must be a string, not JSON "
                f"{json_kind(report_locale)}; is it an inspect.json?"
            )
            raise typer.Exit(2)
        pack = resolve_pack(locale or report_locale, "none in the report; pass --locale")
        if "summary" not in report:
            err_console.print(f"[red]{source} has no 'summary'[/]; is it an inspect.json?")
            raise typer.Exit(2)
        summary = report["summary"]

    try:
        rec = decide(summary, pack, Constraints(goals=tuple(goal or ()), gpu=gpu, duplex=duplex))
    except ValidationError as exc:
        # Only a hand-edited or foreign report can get here: `inspect` writes the shape
        # this checks. Name the first bad field rather than printing pydantic's dump.
        first = exc.errors()[0]
        where = ".".join(str(p) for p in ("summary", *first["loc"]))
        err_console.print(f"[red]{source}: {where}[/]: {first['msg']}; is it an inspect.json?")
        raise typer.Exit(2) from None

    table = Table(
        title=f"recommendation · locale {pack.id}", title_justify="left", show_header=False
    )
    table.add_column(style="dim")
    table.add_column()
    table.add_row("primary problem", rec.primary_problem or "none yet: no usable evidence")
    table.add_row("goals", ", ".join(rec.goals) or "-")
    for r in rec.routes:
        table.add_row(r.source, f"[bold]{r.route}[/]  {r.why}")
    colours = {"blocked": "red", "baseline_first": "yellow", "candidate": "green"}
    verdicts = {k: f"[bold {colours[k]}]{label}[/]" for k, label in VERDICT_LABELS.items()}
    table.add_row("fine-tune?", f"{verdicts[rec.fine_tune]}  {rec.fine_tune_reason}")
    console.print(table)

    # One block per goal. A project with two goals is two questions with two answers, and
    # printing only the first one is how "recognition" used to disappear from the report.
    for d in rec.goal_decisions:
        goal = Table(title=f"goal · {d.goal}", title_justify="left", show_header=False)
        goal.add_column(style="dim")
        goal.add_column()
        goal.add_row("fine-tune?", f"{verdicts[d.eligibility]}  {d.reason}")
        if d.need is not None:
            goal.add_row(
                f"data ({d.unit})",
                f"{fmt_number(d.have)} of ~{fmt_number(d.need)}  from {d.have_from}",
            )
        for note in d.uncounted:
            goal.add_row("[yellow]not counted[/]", note)
        for blocker in d.blockers:
            goal.add_row("[yellow]blocked on[/]", blocker)
        goal.add_row("recipe", f"{d.recipe or 'none'}  {d.recipe_reason}")
        if d.recipe_method:
            # The recipes are researched, not built; the method is their plan, not a result.
            goal.add_row("method", f"{d.recipe_method}  [dim](planned, not yet run)[/]")
        # The confidence label matters as much as the verdict: a threshold we invented and
        # one a paper measured should not read the same way.
        goal.add_row(f"evidence ({d.confidence})", d.evidence)
        console.print(goal)
    if rec.consent:
        console.print("[bold]consent and privacy[/] (not legal advice)")
        for line in rec.consent:
            console.print(f"  • {line}")
    console.print("[bold]next steps[/]")
    for i, step in enumerate(rec.next_steps, 1):
        console.print(f"  {i}. {step}")
    # The output uses its own vocabulary (turns, floor, baseline first); say where it's defined.
    console.print(f"[dim]what these terms mean: {GLOSSARY_URL}[/]")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"locale": pack.id, **rec.to_dict()}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    console.print(f"[green]wrote[/] {out}")


@app.command()
def report(
    inspect_json: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="inspect.json from `inspect`.")
    ] = Path("inspect.json"),
    recommend_json: Annotated[
        Path | None,
        typer.Argument(exists=True, dir_okay=False, help="recommend.json, to add the decision."),
    ] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the page.")] = Path(
        "report.html"
    ),
) -> None:
    """Write one HTML page from inspect.json (and recommend.json) to share or save as PDF."""
    from vakforge.html_report import render

    data = _read_json_object(inspect_json, "an inspect.json")
    if not isinstance(data.get("summary"), dict) or not isinstance(data.get("files"), list):
        err_console.print(
            f"[red]{inspect_json} has no summary and files[/]; is it an inspect.json?"
        )
        raise typer.Exit(2)
    rec = None
    if recommend_json:
        rec = _read_json_object(recommend_json, "a recommend.json")
        if "goal_decisions" not in rec:
            err_console.print(
                f"[red]{recommend_json} has no goal_decisions[/]; is it a recommend.json?"
            )
            raise typer.Exit(2)
        if rec.get("locale") != data.get("locale"):
            err_console.print(
                f"[yellow]warning:[/] {recommend_json} is for locale {rec.get('locale')}, "
                f"{inspect_json} for {data.get('locale')}; are they from the same folder?"
            )
    try:
        page = render(data, rec)
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        # Only a hand-edited or foreign file gets here: inspect and recommend write the
        # shape the page reads.
        err_console.print(
            f"[red]cannot build the page[/]: {type(exc).__name__}: {exc}; were both files "
            "written by vakforge?"
        )
        raise typer.Exit(2) from None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    console.print(f"[green]wrote[/] {out}  (open it in a browser; print it to save a PDF)")


@app.command()
def locales(
    pack_id: Annotated[
        str | None, typer.Argument(help="Show one pack in detail, e.g. hi-Latn-IN.")
    ] = None,
) -> None:
    """List locale packs, or show one pack's formats, PII patterns, consent and recipe support."""
    from rich.table import Table

    from vakforge.locales import get_pack, list_packs

    if pack_id is None:
        table = Table(title="Locale packs", title_justify="left")
        for col in ("id", "name", "parent", "languages", "consent", "PII types"):
            table.add_column(col)
        for pid in list_packs():
            p = get_pack(pid)
            table.add_row(
                pid,
                p.name,
                p.parent or "",
                ", ".join(sorted(p.all_languages())),
                p.resolved("call_recording_consent") or "",
                str(len(p.all_pii_patterns())),
            )
        console.print(table)
        return

    try:
        p = get_pack(pack_id)
    except KeyError as exc:
        err_console.print(f"[red]{exc.args[0]}[/]")
        raise typer.Exit(2) from None

    fmt = p.resolved("formats")
    notes = p.resolved("privacy_notes")
    console.print(f"[bold]{p.id}[/] {p.name}" + (f"  (inherits {p.parent})" if p.parent else ""))
    console.print(f"languages: {', '.join(sorted(p.all_languages()))}")
    if fmt:
        console.print(
            f"currency: {' '.join(fmt.currency_symbols)} ({', '.join(fmt.currency_words)})"
            f" · dates {fmt.date_order} · phone e.g. {fmt.phone_example}"
            f" · postal e.g. {fmt.postal_example}"
        )
    console.print(f"PII: {', '.join(pat.name for pat in p.all_pii_patterns())}")
    console.print(f"call-recording consent: {p.resolved('call_recording_consent') or 'not set'}")
    support = p.resolved("recipe_support")
    if support:
        console.print("recipes: " + ", ".join(f"{r}={s}" for r, s in support.items()))
    if notes:
        console.print(f"privacy (not legal advice): {notes.summary}")
        for link in notes.links:
            console.print(f"  {link}")


if __name__ == "__main__":
    app()
