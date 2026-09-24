"""Renderer: Deck Plan + Format Pack -> native .pptx (Phase 1C).

Public API:
- :func:`render_deck` — turn a :class:`DeckPlan` into a .pptx file.
- :class:`RenderResult` — outcome object (path, slide count, warnings).
- :func:`canvas_size` — aspect-ratio string to (width, height) in EMU.
- :func:`save_pack` / :func:`load_pack` / :func:`export_dfpack` /
  :func:`load_dfpack` / :func:`list_packs` — pack on-disk format + .dfpack.
"""

from __future__ import annotations

from deckforge_core.renderer.canvas import (  # noqa: F401
    Canvas,
    canvas_size,
    emu_to_inch,
    emu_to_relative,
    font_pt_to_emu,
    inch_to_emu,
    relative_to_emu,
)
from deckforge_core.renderer.engine import RenderResult, render_deck  # noqa: F401
from deckforge_core.renderer.pack_io import (  # noqa: F401
    export_dfpack,
    list_packs,
    load_dfpack,
    load_pack,
    save_pack,
)

__all__ = [
    "Canvas",
    "RenderResult",
    "canvas_size",
    "emu_to_inch",
    "emu_to_relative",
    "export_dfpack",
    "font_pt_to_emu",
    "inch_to_emu",
    "list_packs",
    "load_dfpack",
    "load_pack",
    "relative_to_emu",
    "render_deck",
    "save_pack",
]
