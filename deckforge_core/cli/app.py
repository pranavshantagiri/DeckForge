"""DeckForge CLI (Typer).

Mode commands land with their workstreams: learn (A), make (C+D),
restyle/outline/critique/blend/edit (Phase 2), packs/settings housekeeping.
Every command is a thin call into ``deckforge_core.modes``; nothing stateful
lives here.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from deckforge_core import __version__
from deckforge_core.config import data_dir, ensure_dirs
from deckforge_core.errors import DeckForgeError
from deckforge_core.modes import (
    ModeError,
    run_blend,
    run_critique,
    run_edit,
    run_learn,
    run_make,
    run_outline,
    run_restyle,
)

app = typer.Typer(
    name="deckforge",
    help="Learn presentation formats from real decks, generate human-looking decks.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _fail(message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(1)


# --------------------------------------------------------------------------- #
# Top-level
# --------------------------------------------------------------------------- #
@app.command("version")
def version() -> None:
    """Print DeckForge version and environment summary."""
    typer.echo(f"DeckForge {__version__}")
    typer.echo(f"data dir: {data_dir()}")
    from deckforge_core.providers.render import RendererAutodetect

    det = RendererAutodetect()
    typer.echo(f"slide renderers: {[b.value for b in det.available]}")


@app.command("about")
def about() -> None:
    """Show what DeckForge is."""
    typer.echo(
        "DeckForge learns a Format Pack from hundreds of real .pptx decks, then "
        "plans and renders new native, editable decks in that format."
    )


@app.command("learn", no_args_is_help=True)
def learn(
    source: str = typer.Argument(..., help="Folder containing .pptx decks"),
    name: str = typer.Option("", "--name", "-n", help="Pack name (default: source folder name)"),
    use_cache: bool = typer.Option(True, "--use-cache/--no-cache", help="Reuse analysed slides"),
    max_decks: int = typer.Option(0, "--max-decks", help="Cap how many decks are analysed (0 = all)"),
) -> None:
    """Build a Format Pack from real decks."""
    try:
        pack_name = name or Path(source).name
        result = run_learn(source, pack_name, use_cache=use_cache, max_decks=max_decks)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))

    table = Table(title=f"Format Pack [bold]{result.pack.name}[/bold]")
    table.add_column("deck count")
    table.add_column("slides")
    table.add_column("archetypes")
    table.add_column("aspect")
    table.add_column("confidence")
    table.add_row(
        str(result.decks),
        str(result.slides),
        str(len(result.pack.archetypes)),
        ",".join(result.pack.aspect_ratios),
        f"{result.pack.style.confidence.overall:.0%}",
    )
    console.print(table)
    console.print(f"[green]saved:[/green] {result.pack_dir}")


@app.command("make", no_args_is_help=True)
def make(
    prompt: str = typer.Argument(..., help="Brief / prompt describing the deck"),
    pack_spec: str = typer.Option("demo", "--pack", "-p", help="Pack name or path (default: demo)"),
    slides: int = typer.Option(10, "--slides", "--n", help="Number of slides"),
    tone: str = typer.Option("professional", "--tone", help="tone (professional/data-driven/...)"),
    audience: str = typer.Option("", "--audience", help="Audience description"),
    aspect: str = typer.Option("16:9", "--aspect", help="Aspect ratio, e.g. 16:9, 4:3"),
    provider: str = typer.Option(None, "--provider", help="Planner provider (default: settings)"),
    out: str = typer.Option("", "--out", "-o", help="Output .pptx path (default: data dir)"),
    save_plan: str = typer.Option("", "--save-plan", help="Also write the DeckPlan JSON here"),
) -> None:
    """Plan + render a deck in a learned Format Pack."""
    if not out:

        out = str(ensure_dirs()["decks"] / _slug(prompt))
    warnings: list[str] = []
    try:
        result = run_make(
            prompt,
            pack_spec,
            out,
            slides=slides,
            tone=tone,
            audience=audience,
            aspect=aspect,
            provider=provider or None,
            save_plan=save_plan or None,
            warnings=warnings,
        )
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))

    table = Table(title=f"Deck from pack [bold]{result.plan.pack}[/bold]")
    table.add_column("slides")
    table.add_column("size")
    table.add_column("archetypes")
    table.add_row(
        str(result.slide_count),
        f"{result.width:.0f}x{result.height:.0f} px",
        ",".join({s.archetype for s in result.plan.slides}),
    )
    console.print(table)
    for warn in warnings:
        err_console.print(f"[yellow]warning:[/yellow] {warn}")
    console.print(f"[green]saved:[/green] {result.out_path}")


@app.command("restyle", no_args_is_help=True)
def restyle(
    deck_path: str = typer.Argument(..., help="Existing .pptx to re-render"),
    pack_spec: str = typer.Option("demo", "--pack", "-p", help="Pack name or path (default: demo)"),
    out: str = typer.Option("", "--out", "-o", help="Output .pptx path"),
) -> None:
    """Re-render an existing deck in a new Format Pack."""
    if not out:

        out = str(ensure_dirs()["decks"] / (_slug(deck_path) + "-restyled"))
    warnings: list[str] = []
    try:
        result = run_restyle(deck_path, pack_spec, out, warnings=warnings)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    for warn in warnings:
        err_console.print(f"[yellow]warning:[/yellow] {warn}")
    console.print(f"[green]restyled:[/green] {result.out_path} ({result.slide_count} slides)")


@app.command("outline", no_args_is_help=True)
def outline(
    prompt: str = typer.Argument(..., help="Brief / prompt describing the deck"),
    pack_spec: str = typer.Option("demo", "--pack", "-p", help="Pack name or path (default: demo)"),
    slides: int = typer.Option(10, "--slides", "--n", help="Number of slides"),
    tone: str = typer.Option("professional", "--tone", help="tone (professional/data-driven/...)"),
    audience: str = typer.Option("", "--audience", help="Audience description"),
    aspect: str = typer.Option("16:9", "--aspect", help="Aspect ratio, e.g. 16:9, 4:3"),
    provider: str = typer.Option(None, "--provider", help="Planner provider (default: settings)"),
) -> None:
    """Preview the structure that a prompt + pack would produce."""
    try:
        lines = run_outline(
            prompt,
            pack_spec,
            slides=slides,
            tone=tone,
            audience=audience,
            aspect=aspect,
            provider=provider or None,
        )
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    for line in lines:
        console.print(f"[dim]{line.n:>2}.[/dim] {line.archetype:<20} {line.title}")


@app.command("critique", no_args_is_help=True)
def critique(
    deck_path: str = typer.Argument(..., help=".pptx or DeckPlan JSON to review"),
    pack_spec: str = typer.Option("demo", "--pack", "-p", help="Pack name or path (default: demo)"),
    render_backend: str = typer.Option("none", "--render-backend", help="none|auto|powerpoint-com"),
) -> None:
    """Run QA checks on a deck through a Format Pack."""
    out_dir = ensure_dirs()["renders"] / "critique"
    try:
        report = run_critique(deck_path, pack_spec, out_dir=out_dir, render_backend=render_backend)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))

    status = "[bold green]PASS[/bold green]" if report.passed_check else "[bold red]FAIL[/bold red]"
    console.print(
        f"QA {status}: {report.errors_total()} errors, "
        f"{report.warnings_total()} warnings, rendered={report.rendered}"
    )
    for slide in report.slides:
        if not slide.issues:
            continue
        console.print(f"[dim]slide {slide.slide_n}:[/dim]")
        for issue in slide.issues:
            color = "red" if issue.severity.value == "error" else "yellow"
            console.print(f"  [{color}]{issue.severity.value}[/{color}] [{issue.check.value}] {issue.message}")


@app.command("blend", no_args_is_help=True)
def blend(
    pack_a: str = typer.Argument(..., help="First pack name or path"),
    pack_b: str = typer.Argument(..., help="Second pack name or path"),
    name: str = typer.Option("", "--name", "-n", help="New pack name (required)"),
) -> None:
    """Merge two Format Packs (palette averaged, archetype sheets united)."""
    if not name:
        _fail("--name is required")
    try:
        result = run_blend(pack_a, pack_b, name)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    table = Table(title=f"Blended pack [bold]{result.name}[/bold]")
    table.add_column("archetypes")
    table.add_column("source decks")
    table.add_column("slides")
    table.add_row(str(len(result.archetypes)), str(result.decks), str(result.slides))
    console.print(table)
    console.print(f"[green]saved:[/green] {result.pack_dir}")


@app.command("edit", no_args_is_help=True)
def edit(
    plan_json: str = typer.Argument(..., help="DeckPlan JSON (e.g. from --save-plan)"),
    edits: list[str] = typer.Option(..., "-e", "--edit", help="SLIDE:SLOT[.FIELD]=VALUE"),
    pack_spec: str = typer.Option("", "--pack", "-p", help="Pack name or path (default: plan's pack)"),
    out: str = typer.Option("", "--out", "-o", help="Output .pptx path (default: data dir)"),
) -> None:
    """Load a saved plan, apply slot edits, re-render."""
    if not out:
        from pathlib import Path

        base = Path(plan_json).stem
        out = str(ensure_dirs()["decks"] / f"{base}-edited")
    warnings: list[str] = []
    try:
        result = run_edit(
            plan_json,
            edits,
            out,
            pack_spec=pack_spec or None,
            warnings=warnings,
        )
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    for warn in warnings:
        err_console.print(f"[yellow]warning:[/yellow] {warn}")
    console.print(
        f"[green]applied {result.applied} edit(s) ->[/green] {result.render.out_path} "
        f"({result.render.slide_count} slides)"
    )


# --------------------------------------------------------------------------- #
# packs sub-command
# --------------------------------------------------------------------------- #
packs_app = typer.Typer(help="List, inspect, and remove Format Packs.", no_args_is_help=True)
app.add_typer(packs_app, name="packs")


@packs_app.command("list")
def packs_list() -> None:
    """List installed packs."""
    from deckforge_core.modes import list_packs

    names = list_packs()
    if not names:
        console.print("[dim]no packs yet — run `deckforge learn SOURCE --name NAME`[/dim]")
        return
    table = Table("name", "path")
    for n in names:
        table.add_row(n, str(ensure_dirs()["packs"] / n))
    console.print(table)


@packs_app.command("show")
def packs_show(name: str = typer.Argument(...)) -> None:
    """Show details of one pack."""
    from deckforge_core.modes.packs import cmd_show

    try:
        summary = cmd_show(name)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    console.print(f"[bold]{summary.pack.name}[/bold] — {summary.decks} decks, {summary.slides} slides")
    console.print(f"archetypes: {', '.join(summary.pack.archetypes)}")
    console.print(
        f"palette: {', '.join(c.hex for c in summary.pack.style.palette.colors[:5])} "
        f"(confidence {summary.pack.style.confidence.overall:.0%})"
    )
    console.print(f"path: {summary.pack_dir}")


@packs_app.command("delete")
def packs_delete(name: str = typer.Argument(...), yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Delete a pack from the data directory."""
    if not yes:
        _fail("use --yes to confirm deletion")
    from deckforge_core.modes.packs import cmd_delete

    try:
        cmd_delete(name)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    console.print(f"[green]deleted pack {name}[/green]")


@packs_app.command("path")
def packs_path(name: str = typer.Argument(...)) -> None:
    """Print the on-disk location of a pack."""
    from deckforge_core.modes.packs import cmd_path

    try:
        console.print(cmd_path(name))
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))


# --------------------------------------------------------------------------- #
# settings sub-command
# --------------------------------------------------------------------------- #
settings_app = typer.Typer(help="View and change persisted settings.", no_args_is_help=True)
app.add_typer(settings_app, name="settings")


@settings_app.command("list")
def settings_list() -> None:
    """List all saved settings."""
    from deckforge_core.modes.settings_cmd import cmd_list

    values = cmd_list()
    table = Table("key", "value")
    for key, value in sorted(values.items()):
        table.add_row(key, _repr_value(value))
    console.print(table)


@settings_app.command("get")
def settings_get(key: str = typer.Argument(...)) -> None:
    """Print one setting's value."""
    from deckforge_core.modes.settings_cmd import cmd_get

    console.print(_repr_value(cmd_get(key)))


@settings_app.command("set")
def settings_set(key: str = typer.Argument(...), value: str = typer.Argument(...)) -> None:
    """Set a non-secret setting (booleans/ints/floats auto-parsed)."""
    from deckforge_core.modes.settings_cmd import cmd_set

    try:
        stored = cmd_set(key, value)
    except (ModeError, DeckForgeError) as exc:
        _fail(str(exc))
    console.print(f"{key} = {_repr_value(stored)}")


@settings_app.command("unset")
def settings_unset(key: str = typer.Argument(...)) -> None:
    """Reset a setting to its default."""
    from deckforge_core.modes.settings_cmd import cmd_unset

    cmd_unset(key)
    console.print(f"reset {key} to default")


@app.command("provider")
def provider(
    name: str = typer.Argument(..., help="Provider key, e.g. anthropic"),
    api_key: str = typer.Option("", "--api-key", help="API key (NOT stored on disk settings)",
                                prompt=False),
) -> None:
    """Store an API key in the OS credential manager (not on disk)."""
    from deckforge_core.config import SecretStore

    store = SecretStore()
    if api_key:
        store.set(name, api_key)
        console.print(f"[green]stored credential for {name} in the OS keyring[/green]")
        return
    existing = store.get(name)
    console.print(
        f"{name}: credential {'present' if existing else 'absent'} "
        "(use --api-key to set, never shown back)"
    )


def _slug(text: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:48] or "deck"


def _repr_value(value) -> str:
    if isinstance(value, str):
        return value
    import json

    return json.dumps(value)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
