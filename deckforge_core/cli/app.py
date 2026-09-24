"""DeckForge CLI (Typer). Mode commands land with their workstreams:
learn (A), make (C+D), restyle/outline/critique/blend/edit (Phase 2)."""

from __future__ import annotations

import typer

from deckforge_core import __version__

app = typer.Typer(
    name="deckforge",
    help="Learn presentation formats from real decks, generate human-looking decks.",
    no_args_is_help=True,
)


@app.command("version")
def version() -> None:
    """Print DeckForge version and environment summary."""
    typer.echo(f"DeckForge {__version__}")
    from deckforge_core.config import data_dir

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
