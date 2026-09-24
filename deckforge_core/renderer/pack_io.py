"""On-disk format for Format Packs: pack directory + ``.dfpack`` zip.

Layout of a pack directory::

    pack.json               FormatPack metadata (style embedded)
    style_profile.json      StyleProfile standalone copy
    manifest.json           name / version / format_version
    blueprints/<id>.json    one Blueprint per archetype
    theme/                  presentation-theme notes (placeholder)
    examples/               sample-deck notes (placeholder)
    index/                  search index scratch space (placeholder)

A ``.dfpack`` file is a zip of exactly that layout (``.dfpack`` export/import
keeps packs portable). The renderer never needs this module — pack authoring
and the CLI do.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import List, Tuple

from deckforge_core.schemas.blueprints import Blueprint, BlueprintLibrary
from deckforge_core.schemas.pack import PACK_SCHEMA_VERSION as _PACK_FORMAT
from deckforge_core.schemas.pack import FormatPack

_MANIFEST_NAME = "manifest.json"
_PLACEHOLDER_DOCS = {
    "theme": "Theme assets for this pack.\n",
    "examples": "Example decks/previews produced with this pack.\n",
    "index": "Search/QA index scratch space for this pack.\n",
}


def save_pack(pack: FormatPack, blueprints: BlueprintLibrary, pack_dir: Path) -> None:
    """Write ``pack`` + ``blueprints`` into ``pack_dir`` (created if needed)."""
    pack_dir = Path(pack_dir)
    for sub in ("blueprints", *sorted(_PLACEHOLDER_DOCS)):
        (pack_dir / sub).mkdir(parents=True, exist_ok=True)

    pack_json = pack.model_dump(mode="json")
    _write_json(pack_dir / "pack.json", pack_json)
    _write_json(pack_dir / "style_profile.json", pack.style.model_dump(mode="json"))
    _write_json(
        pack_dir / _MANIFEST_NAME,
        {
            "format_version": pack.format_version,
            "name": pack.name,
            "version": pack.version,
        },
    )
    for blueprint in blueprints.all():
        blueprint_path = pack_dir / "blueprints" / f"{_safe_id(blueprint.id)}.json"
        _write_json(blueprint_path, blueprint.model_dump(mode="json"))

    for sub, text in _PLACEHOLDER_DOCS.items():
        _write_text(pack_dir / sub / "README.txt", text)


def load_pack(pack_dir: Path) -> Tuple[FormatPack, BlueprintLibrary]:
    """Load a ``FormatPack`` + ``BlueprintLibrary`` saved by :func:`save_pack`."""
    pack_dir = Path(pack_dir)
    pack = FormatPack.model_validate(_read_json(pack_dir / "pack.json"))
    blueprints: List[Blueprint] = []
    blueprints_dir = pack_dir / "blueprints"
    if blueprints_dir.is_dir():
        for blueprint_file in sorted(blueprints_dir.glob("*.json")):
            blueprints.append(Blueprint.model_validate(_read_json(blueprint_file)))
    return pack, BlueprintLibrary(blueprints)


def export_dfpack(pack_dir: Path, zip_path: Path) -> None:
    """Package a saved pack directory into a portable ``.dfpack`` zip."""
    pack_dir = Path(pack_dir).resolve()
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "format_version": _PACK_FORMAT,
        "name": "",
        "version": "",
    }
    pack_file = pack_dir / "pack.json"
    if pack_file.is_file():
        pack_data = _read_json(pack_file)
        manifest = {
            "format_version": pack_data.get("format_version", _PACK_FORMAT),
            "name": pack_data.get("name", ""),
            "version": pack_data.get("version", ""),
        }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_MANIFEST_NAME, json.dumps(manifest, indent=2))
        for file_path in sorted(pack_dir.rglob("*")):
            if not file_path.is_file() or file_path.name == _MANIFEST_NAME:
                continue
            archive.write(file_path, file_path.relative_to(pack_dir).as_posix())


def load_dfpack(zip_path: Path, dest_dir: Path) -> Tuple[FormatPack, BlueprintLibrary]:
    """Extract a ``.dfpack`` zip into ``dest_dir`` and load the pack."""
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(dest_dir)
    return load_pack(dest_dir)


def list_packs(data_root: Path) -> List[str]:
    """Names (directory names) of packs under ``data_root``."""
    root = Path(data_root)
    if not root.is_dir():
        return []
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / "pack.json").is_file()
    )


# --------------------------------------------------------------------------- #
# Small JSON/text helpers
# --------------------------------------------------------------------------- #
def _safe_id(identifier: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "-", identifier)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
