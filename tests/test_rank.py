"""Ranking, quality filters and attribution tests (offline, PIL-generated)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from deckforge_core.images.attribution import (
    attribution_footer,
    caption_line,
    license_note,
)
from deckforge_core.images.rank import (
    QualityFilter,
    has_acceptable_aspect,
    is_large_enough,
    looks_watermarked,
    pick_best,
    rank_results,
)
from deckforge_core.providers.images import ImageItem


def item(pid: str, w: int, h: int, color: str = "", provider: str = "unsplash") -> ImageItem:
    return ImageItem(
        id=pid,
        provider=provider,
        url=f"https://x/{pid}.jpg",
        width=w,
        height=h,
        color=color,
        attribution=(
            f"Photo by {pid} on Unsplash" if provider == "unsplash" else "Local library photo"
        ),
    )


def test_is_large_enough():
    assert is_large_enough(item("ok", 800, 600), 800, 600)
    assert is_large_enough(item("big", 1920, 1080), 800, 600)
    assert not is_large_enough(item("narrow", 799, 600), 800, 600)
    assert not is_large_enough(item("short", 800, 599), 800, 600)
    assert QualityFilter.is_large_enough(item("ok", 800, 600), 800, 600)


def test_has_acceptable_aspect():
    assert has_acceptable_aspect(item("wide", 1600, 900), 16 / 9)
    assert has_acceptable_aspect(item("square", 400, 400), 1.0)
    assert not has_acceptable_aspect(item("portrait", 800, 1200), 16 / 9)
    assert has_acceptable_aspect(item("nearly", 1200, 800), 16 / 9, tolerance=0.2)
    assert not has_acceptable_aspect(item("nearly", 1200, 800), 16 / 9)
    assert QualityFilter.has_acceptable_aspect(item("wide", 1600, 900), 16 / 9)


def _write(path: Path, im: Image.Image) -> Path:
    im.save(path, "PNG")
    return path


def test_looks_watermarked_detects_repeated_bright_patches(tmp_path):
    watermarked = Image.new("L", (96, 72), 40)
    px = watermarked.load()
    for col in (12, 36, 60, 84):
        for row in (0, 24, 48):
            for y in range(row, row + 12):
                for x in range(col, col + 12):
                    px[x, y] = 255
    assert looks_watermarked(_write(tmp_path / "wm.png", watermarked.convert("RGB")))
    assert QualityFilter.looks_watermarked(_write(tmp_path / "wm2.png", watermarked.convert("RGB")))


def test_looks_watermarked_passes_plain_photos(tmp_path):
    plain = Image.new("L", (96, 72), 128)
    assert not looks_watermarked(_write(tmp_path / "plain.png", plain.convert("RGB")))

    white = Image.new("L", (96, 72), 255)
    assert not looks_watermarked(_write(tmp_path / "white.png", white.convert("RGB")))

    noisy = Image.effect_noise((96, 72), 60).convert("RGB")
    assert not looks_watermarked(_write(tmp_path / "noisy.png", noisy))


def test_rank_results_wider_and_larger_first():
    a = item("a", 1600, 900)
    b = item("b", 1280, 720)
    c = item("c", 800, 600)
    ranked = rank_results([c, b, a], 16 / 9)
    assert [i.id for i in ranked] == ["a", "b", "c"]


def test_rank_results_prefer_wider_vs_area():
    wider = item("wider", 1440, 800)
    bigger = item("bigger", 1400, 1000)
    target = 1.6
    assert [i.id for i in rank_results([bigger, wider], target, prefer_wider=True)] == [
        "wider",
        "bigger",
    ]
    assert [i.id for i in rank_results([bigger, wider], target, prefer_wider=False)] == [
        "bigger",
        "wider",
    ]


def test_rank_results_color_breaks_id_tie():
    red = item("z", 1600, 900, color="#ff0000")
    blue = item("a", 1600, 900, color="#0000ff")
    assert [i.id for i in rank_results([red, blue], 16 / 9, query_color="#ff0000")] == [
        "z",
        "a",
    ]
    assert [i.id for i in rank_results([red, blue], 16 / 9)] == ["a", "z"]


def test_rank_results_color_mismatch_ranks_last():
    red = item("z", 1600, 900, color="#ff0000")
    unknown = item("a", 1600, 900, color="")
    assert [i.id for i in rank_results([red, unknown], 16 / 9, query_color="#00ff00")] == [
        "a",
        "z",
    ]


def test_rank_results_is_deterministic():
    items = [item("c", 800, 600), item("a", 1600, 900), item("b", 1280, 720)]
    first = [i.id for i in rank_results(items, 16 / 9)]
    second = [i.id for i in rank_results(list(reversed(items)), 16 / 9)]
    assert first == second


def test_pick_best_returns_top_ranked():
    items = [item("c", 800, 600), item("a", 1600, 900), item("b", 1280, 720)]
    assert pick_best(items, (1600, 900)).id == "a"
    assert pick_best([], (1600, 900)) is None


def test_attribution_footer_and_caption():
    unsplash = ImageItem(
        id="u1",
        provider="unsplash",
        url="https://x/u1.jpg",
        width=1600,
        height=900,
        attribution="Photo by Jane Doe on Unsplash",
    )
    local = item("l1", 800, 600, provider="local")
    blank = ImageItem(id="b1", provider="unsplash", url="https://x/b1.jpg", width=800, height=600)

    assert attribution_footer(unsplash) == "Photo by Jane Doe on Unsplash"
    assert attribution_footer(local) == "Local library photo"
    assert attribution_footer(blank) == "Photo provided by DeckForge"
    assert caption_line(unsplash) == "Photo by Jane Doe on Unsplash"


def test_license_note():
    unsplash = ImageItem(
        id="u1", provider="unsplash", url="https://x/u1.jpg", width=1600, height=900
    )
    custom = ImageItem(
        id="u2",
        provider="unsplash",
        url="https://x/u2.jpg",
        width=1600,
        height=900,
        license="CC0",
    )
    assert license_note(unsplash) == "Unsplash license"
    assert license_note(custom) == "CC0"
    assert license_note(item("l1", 800, 600, provider="local")) == "local"
