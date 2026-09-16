"""vakforge CLI. Thin: each subcommand delegates to a module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from vakforge import __version__

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
        out.write_text(text + "\n", encoding="utf-8")
        console.print(f"[green]wrote[/] {out}")
    else:
        print(text)


if __name__ == "__main__":
    app()
