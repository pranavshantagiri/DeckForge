"""Canvas geometry tests (Workstream C)."""

from __future__ import annotations

import pytest

from deckforge_core.renderer import (
    Canvas,
    canvas_size,
    emu_to_inch,
    emu_to_relative,
    font_pt_to_emu,
    inch_to_emu,
    relative_to_emu,
)


def test_known_ratios_map_to_emu():
    assert canvas_size("16:9") == (12192000, 6858000)
    assert canvas_size("16:10") == (12192000, 7620000)
    assert canvas_size("4:3") == (9144000, 6858000)
    assert canvas_size("A4") == (7560000, 10692000)
    assert canvas_size("portrait") == (7560000, 10692000)
    assert canvas_size("letter-portrait") == (7772400, 10058400)


def test_px_custom_resolves_at_96dpi():
    assert canvas_size("1920x1080px") == (1920 * 9525, 1080 * 9525)


def test_bare_integer_custom_is_emu():
    assert canvas_size("914400x685800") == (914400, 685800)


def test_portrait_ratio_never_squashes():
    w, h = canvas_size("9:16")  # not a named ratio but clearly portrait
    assert h > w
    assert (w, h) == (7560000, 10692000)


def test_unknown_ratio_falls_back_to_16_9():
    with pytest.warns(RuntimeWarning, match="unknown aspect ratio"):
        assert canvas_size("banana") == (12192000, 6858000)


def test_relative_to_emu_math():
    assert relative_to_emu(0.5, 12192000) == 6096000
    assert relative_to_emu(0.1, 6858000) == 685800
    assert relative_to_emu(0.0, 9144000) == 0
    assert relative_to_emu(1.0, 9144000) == 9144000


def test_emu_to_relative_math():
    assert emu_to_relative(6096000, 12192000) == pytest.approx(0.5)
    assert emu_to_relative(685800, 6858000) == pytest.approx(0.1)


def test_inch_conversions():
    assert inch_to_emu(1.0) == 914400
    assert emu_to_inch(914400) == pytest.approx(1.0)
    assert emu_to_inch(inch_to_emu(2.5)) == pytest.approx(2.5)


def test_font_pt_to_emu():
    assert font_pt_to_emu(72) == 914400  # 1 inch
    assert font_pt_to_emu(1) == 12700


def test_canvas_dataclass():
    canvas = Canvas(12192000, 6858000)
    assert canvas.width_emu == 12192000
    assert canvas.height_emu == 6858000
    assert canvas.aspect_ratio == pytest.approx(16.0 / 9.0)
    assert Canvas.from_ratio("4:3").aspect_ratio == pytest.approx(4.0 / 3.0)
