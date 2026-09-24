"""Slide thumbnails for ingestion/QA previews.

Uses :class:`RendererAutodetect` from the provider registry — never imports
pywin32 directly, so this module imports cleanly on machines with no Office
at all. When the resolved backend is :attr:`RenderBackend.NONE` we return an
empty list (callers handle absent thumbnails) and log a clear message.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from deckforge_core.errors import DeckForgeError
from deckforge_core.logging_util import get_logger
from deckforge_core.providers.render import RenderBackend, RendererAutodetect
from deckforge_core.schemas.extracted import ExtractedDeck

log = get_logger("deckforge.ingest.thumbnails")

DEFAULT_MAX_SIZE = (600, 450)


def render_thumbnails(
    deck: ExtractedDeck,
    out_dir: Path,
    *,
    max_size: tuple[int, int] = DEFAULT_MAX_SIZE,
) -> list[Path]:
    """Render every slide of ``deck`` to a resized PNG under ``out_dir``.

    Returns the produced ``slide_<index>.png`` paths, in slide order. Never
    raises for per-slide renderer failures; on machines with no renderer it
    returns ``[]`` (callers treat missing thumbnails as absent evidence).
    """
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("cannot create thumbnail dir %s: %s", out_dir, exc)
        return []
    src = Path(deck.path)
    try:
        renderer = RendererAutodetect().resolve()
    except DeckForgeError as exc:
        log.warning("no slide renderer resolvable (%s); skipping thumbnails for %s", exc, deck.path)
        return []
    if renderer.backend == RenderBackend.NONE:
        log.warning(
            "no slide renderer installed (powerpoint-com/libreoffice); "
            "no thumbnails for %s — callers should handle absent thumbnails",
            deck.path,
        )
        return []
    if not src.exists():
        log.warning("source deck missing, cannot render thumbnails: %s", deck.path)
        return []
    try:
        rendered = renderer.render(src, out_dir, dpi=72)
    except Exception as exc:
        log.warning("renderer failed for %s: %s", deck.path, exc)
        return []
    produced: list[Path] = []
    for rs in rendered:
        if not rs.image_path:
            continue
        img_path = Path(rs.image_path)
        try:
            with Image.open(img_path) as im:
                im.load()
                im.thumbnail(max_size, Image.Resampling.LANCZOS)
                target = out_dir / f"slide_{rs.number}.png"
                im.convert("RGB").save(target, format="PNG")
                produced.append(target)
        except Exception as exc:
            log.warning(
                "thumbnail for slide %s of %s failed: %s", rs.number, deck.path, exc
            )
            continue
    if not produced:
        log.warning(
            "renderer backend %s produced no thumbnails for %s",
            renderer.backend.value,
            deck.path,
        )
    return produced
