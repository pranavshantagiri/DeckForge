"""`packs`: list, inspect, delete, and export learned Format Packs."""

from __future__ import annotations

import shutil

from deckforge_core.modes.common import (
    LearnSummary,
    ModeError,
    list_packs,
    pack_dir_for,
    packs_root,
    resolve_pack,
    summarize_pack,
)


def cmd_list() -> list[str]:
    return list_packs()


def cmd_show(name: str) -> LearnSummary:
    pack, _ = resolve_pack(name)
    return summarize_pack(pack, pack_dir_for(name))


def cmd_delete(name: str) -> None:
    target = pack_dir_for(name)
    if not (target / "pack.json").is_file():
        raise ModeError(f"pack {name!r} not found")
    shutil.rmtree(target)


def cmd_path(name: str) -> str:
    target = pack_dir_for(name)
    if not (target / "pack.json").is_file():
        raise ModeError(f"pack {name!r} not found")
    return str(target)


def packs_root_dir() -> str:
    return str(packs_root())
