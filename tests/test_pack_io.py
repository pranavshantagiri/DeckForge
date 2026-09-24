"""Pack on-disk format tests (Workstream C)."""

from __future__ import annotations

import json

from deckforge_core.renderer import (
    export_dfpack,
    list_packs,
    load_dfpack,
    load_pack,
    save_pack,
)
from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import (
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
)


def _blueprints():
    return BlueprintLibrary(
        [
            Blueprint(
                id="big-number",
                archetype=Archetype.BIG_NUMBER,
                slots=[
                    SlotDef(
                        name="number",
                        kinds=[ContentKind.NUMBER],
                        region=SlotRegion(x=0.1, y=0.25, w=0.8, h=0.4),
                        style="big-number",
                        align="center",
                        valign="middle",
                    ),
                    SlotDef(
                        name="caption",
                        kinds=[ContentKind.TEXT],
                        region=SlotRegion(x=0.1, y=0.66, w=0.8, h=0.15),
                    ),
                ],
            ),
            Blueprint(
                id="title",
                archetype=Archetype.TITLE,
                slots=[
                    SlotDef(
                        name="title",
                        kinds=[ContentKind.TEXT],
                        region=SlotRegion(x=0.1, y=0.3, w=0.8, h=0.25),
                        style="h1",
                    ),
                ],
            ),
        ]
    )


def test_save_load_roundtrip_preserves_style(canonical_pack, tmp_path):
    pack_dir = tmp_path / "pack"
    blueprints = _blueprints()
    save_pack(canonical_pack, blueprints, pack_dir)

    assert (pack_dir / "pack.json").is_file()
    assert (pack_dir / "style_profile.json").is_file()
    assert (pack_dir / "blueprints" / "big-number.json").is_file()
    assert (pack_dir / "theme" / "README.txt").is_file()

    loaded_pack, loaded_lib = load_pack(pack_dir)
    original_style = json.dumps(canonical_pack.style.model_dump(mode="json"), sort_keys=True)
    loaded_style = json.dumps(loaded_pack.style.model_dump(mode="json"), sort_keys=True)
    assert loaded_style == original_style
    assert loaded_pack.name == canonical_pack.name
    assert loaded_pack.style.palette.hex("accent1") == "#C4472F"
    assert loaded_lib.archetypes() == sorted(b.id for b in blueprints.all())


def test_dfpack_export_then_import_yields_same_pack(canonical_pack, tmp_path):
    pack_dir = tmp_path / "source-pack"
    save_pack(canonical_pack, _blueprints(), pack_dir)

    zip_path = tmp_path / "demo.dfpack"
    export_dfpack(pack_dir, zip_path)
    assert zip_path.is_file()

    import_dir = tmp_path / "imported"
    imported_pack, imported_lib = load_dfpack(zip_path, import_dir)
    assert imported_pack.name == canonical_pack.name
    assert imported_pack.version == canonical_pack.version
    assert imported_pack.format_version == canonical_pack.format_version
    assert imported_pack.style.model_dump() == canonical_pack.style.model_dump()
    assert imported_lib.archetypes() == ["big-number", "title"]


def test_list_packs_finds_saved_pack(canonical_pack, tmp_path):
    data_root = tmp_path / "packs"
    save_pack(canonical_pack, _blueprints(), data_root / "demo")
    save_pack(canonical_pack.model_copy(update={"name": "other"}), _blueprints(), data_root / "alt")

    names = list_packs(data_root)
    assert names == ["alt", "demo"]


def test_list_packs_ignores_non_pack_dirs(tmp_path):
    data_root = tmp_path / "root"
    (data_root / "not-a-pack").mkdir(parents=True)
    assert list_packs(data_root) == []
    assert list_packs(tmp_path / "missing") == []
