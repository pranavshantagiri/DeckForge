"""`blend`: merge two Format Packs into one (palette averaged, sheets union)."""

from __future__ import annotations

from dataclasses import dataclass

from deckforge_core.modes.common import ModeError, pack_dir_for, resolve_pack, save_new_pack
from deckforge_core.schemas.archetypes import ARCHETYPE_ORDER
from deckforge_core.schemas.blueprints import BlueprintLibrary
from deckforge_core.schemas.pack import (
    ColorPalette,
    FormatPack,
    Grid,
    Margins,
    PaletteColor,
    StyleProfile,
)


@dataclass
class BlendResult:
    name: str
    pack_dir: str
    archetypes: list[str]
    decks: int
    slides: int


def run_blend(
    pack_a_spec: str,
    pack_b_spec: str,
    name: str,
) -> BlendResult:
    pack_a, lib_a = resolve_pack(pack_a_spec)
    pack_b, lib_b = resolve_pack(pack_b_spec)
    if name != pack_a.name and name != pack_b.name and (pack_dir_for(name) / "pack.json").is_file():
        raise ModeError(f"a pack named {name!r} already exists")

    leader = pack_a if _confidence(pack_a) >= _confidence(pack_b) else pack_b
    style = _blend_style(pack_a.style, pack_b.style, leader.style)
    archetypes = sorted(set(pack_a.archetypes) | set(pack_b.archetypes))

    blended = FormatPack(
        name=name,
        source_deck_count=pack_a.source_deck_count + pack_b.source_deck_count,
        source_slide_count=pack_a.source_slide_count + pack_b.source_slide_count,
        aspect_ratios=sorted(set(pack_a.aspect_ratios) | set(pack_b.aspect_ratios)),
        archetypes=archetypes,
        default_archetype_order=[
            a for a in ARCHETYPE_ORDER if a in archetypes
        ],
        style=style,
    )

    library = _blend_library(pack_a, lib_a, pack_b, lib_b, leader.name)
    save_new_pack(name, blended, library)
    return BlendResult(
        name=name,
        pack_dir=str(pack_dir_for(name)),
        archetypes=archetypes,
        decks=blended.source_deck_count,
        slides=blended.source_slide_count,
    )


def _confidence(pack: FormatPack) -> float:
    return float(pack.style.confidence.overall)


def _blend_style(
    a: StyleProfile, b: StyleProfile, leader: StyleProfile
) -> StyleProfile:
    palette = _blend_palette(a.palette, b.palette)
    return StyleProfile(
        palette=palette,
        fonts=leader.fonts,
        type_scale=leader.type_scale,
        margins=Margins(
            left=(a.margins.left + b.margins.left) / 2,
            right=(a.margins.right + b.margins.right) / 2,
            top=(a.margins.top + b.margins.top) / 2,
            bottom=(a.margins.bottom + b.margins.bottom) / 2,
        ),
        grid=Grid(
            columns=leader.grid.columns,
            gutter=(a.grid.gutter + b.grid.gutter) / 2,
            baseline_step=leader.grid.baseline_step,
        ),
        corner_radii=(a.corner_radii + b.corner_radii) / 2,
        line_weight_pt=(a.line_weight_pt + b.line_weight_pt) / 2,
        image_treatment=leader.image_treatment,
        density=leader.density,
        confidence=leader.confidence,
        notes=list(a.notes or []) + ["blended from two packs"],
    )


def _blend_palette(a: ColorPalette, b: ColorPalette) -> ColorPalette:
    by_role: dict[str, list[PaletteColor]] = {}
    for palette in (a, b):
        for color in palette.colors:
            by_role.setdefault(color.role, []).append(color)

    rows = []
    for role, items in by_role.items():
        hex_a = items[0].hex
        hex_b = items[1].hex if len(items) > 1 else hex_a
        rows.append(
            PaletteColor(
                role=role,
                hex=_avg_hex(hex_a, hex_b),
                usage_pct=round(sum(c.usage_pct for c in items) / len(items), 2),
            )
        )
    rows.sort(key=lambda c: c.usage_pct, reverse=True)
    return ColorPalette(colors=rows)


def _avg_hex(a: str, b: str) -> str:
    def _chunks(hexstr: str) -> tuple[int, int, int]:
        h = hexstr.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    ra, ga, ba = _chunks(a)
    rb, gb, bb = _chunks(b)
    return "#{:02X}{:02X}{:02X}".format(
        round((ra + rb) / 2), round((ga + gb) / 2), round((ba + bb) / 2)
    )


def _blend_library(
    pack_a: FormatPack,
    lib_a: BlueprintLibrary,
    pack_b: FormatPack,
    lib_b: BlueprintLibrary,
    leader_name: str,
) -> BlueprintLibrary:
    leader_lib = lib_a if leader_name == pack_a.name else lib_b
    other_lib = lib_b if leader_name == pack_a.name else lib_a
    chosen: dict[str, object] = {}
    for archetype in set(pack_a.archetypes) | set(pack_b.archetypes):
        chosen[archetype] = leader_lib.get(archetype) or other_lib.get(archetype)
    return BlueprintLibrary(list(chosen.values()))
