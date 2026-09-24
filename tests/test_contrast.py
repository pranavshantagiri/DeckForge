"""WCAG contrast helpers: known values and pass/fail behaviour."""

from __future__ import annotations

from deckforge_core.theme.contrast import (
    accessible_text_colors,
    contrast_ratio,
    is_pass,
    relative_luminance,
)


def test_contrast_ratio_white_black_is_21():
    assert abs(contrast_ratio("#FFFFFF", "#000000") - 21.0) < 0.01


def test_contrast_ratio_is_symmetric():
    a, b = "#C4472F", "#FFFFFF"
    assert abs(contrast_ratio(a, b) - contrast_ratio(b, a)) < 1e-9


def test_relative_luminance_bounds():
    assert relative_luminance("#000000") < 1e-6
    assert abs(relative_luminance("#FFFFFF") - 1.0) < 1e-6


def test_known_pair_contrast_positive():
    assert contrast_ratio("#C4472F", "#FFFFFF") > 0
    assert contrast_ratio("#C4472F", "#1C1C1A") > 0


def test_near_black_on_white_passes_large_and_normal():
    assert is_pass("#FFFFFF", "#1C1C1A") is True
    assert is_pass("#FFFFFF", "#1C1C1A", large=True) is True


def test_grey_on_white_fails_normal_text():
    assert is_pass("#C0C0C0", "#FFFFFF") is False


def test_mid_grey_on_white_passes_large_graphics_only():
    assert is_pass("#777777", "#FFFFFF") is False
    assert is_pass("#777777", "#FFFFFF", large=True) is True


def test_accessible_text_on_dark_bg_includes_white():
    assert "#FFFFFF" in accessible_text_colors("#1C1C1A")


def test_accessible_text_on_light_bg_includes_near_black():
    assert accessible_text_colors("#FFFFFF")[0] == "#1C1C1A"


def test_accessible_text_sorted_by_contrast():
    colors = accessible_text_colors("#C0C0C0")
    ratios = [contrast_ratio(c, "#C0C0C0") for c in colors]
    assert ratios == sorted(ratios, reverse=True)
