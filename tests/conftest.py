"""Shared pytest fixtures. The data contracts must round-trip JSON; these
factories build canonical instances used across all workstream tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from deckforge_core.schemas.pack import (
    ColorPalette,
    FontPair,
    FormatPack,
    Grid,
    ImageTreatment,
    Margins,
    PaletteColor,
    StyleConfidence,
    StyleProfile,
    TypeScale,
    TypeScaleEntry,
)


@pytest.fixture(scope="session")
def tmp_workspace() -> Path:
    with tempfile.TemporaryDirectory(prefix="deckforge-test-") as td:
        yield Path(td)


@pytest.fixture
def canonical_style() -> StyleProfile:
    return StyleProfile(
        palette=ColorPalette(
            colors=[
                PaletteColor(role="bg", hex="#FAFAF7", usage_pct=40.0),
                PaletteColor(role="text", hex="#1C1C1A", usage_pct=25.0),
                PaletteColor(role="accent1", hex="#C4472F", usage_pct=12.0),
                PaletteColor(role="accent2", hex="#2F6F8F", usage_pct=8.0),
                PaletteColor(role="muted-text", hex="#6B6B66", usage_pct=15.0),
            ]
        ),
        fonts=FontPair(heading="Arial", body="Arial", heading_usage_pct=55.0, body_usage_pct=45.0),
        type_scale=TypeScale(
            entries=[
                TypeScaleEntry(name="h1", size_pt=40, weight="bold"),
                TypeScaleEntry(name="h2", size_pt=28, weight="bold"),
                TypeScaleEntry(name="kicker", size_pt=12, weight="medium", caps="upper"),
                TypeScaleEntry(name="body", size_pt=16, weight="regular", line_spacing=1.2),
                TypeScaleEntry(name="small", size_pt=12, weight="regular"),
                TypeScaleEntry(name="big-number", size_pt=80, weight="bold"),
                TypeScaleEntry(name="caption", size_pt=10, weight="regular"),
            ]
        ),
        margins=Margins(),
        grid=Grid(columns=12),
        corner_radii=0.02,
        line_weight_pt=1.0,
        image_treatment=ImageTreatment(mode="framed", corner_radius=0.02),
        confidence=StyleConfidence(overall=0.9, palette=0.9, fonts=0.85, grid=0.8, layout=0.85),
        density={},
        notes=["built from sample corpus"],
    )


@pytest.fixture
def canonical_pack(canonical_style: StyleProfile) -> FormatPack:
    return FormatPack(
        name="demo",
        version="1.0",
        source_deck_count=3,
        source_slide_count=60,
        aspect_ratios=["16:9", "4:3"],
        archetypes=["title", "big-number", "two-column-text", "three-cards"],
        default_archetype_order=["title", "big-number", "two-column-text", "three-cards"],
        style=canonical_style,
    )
