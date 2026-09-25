"""Phase 2 mode commands: thin, deterministic wrappers over the core APIs.

Each module exposes a single ``run_*`` function that the CLI calls; the GUI
reuses them too. Modes never print — they return data.
"""

from deckforge_core.modes.blend import BlendResult, run_blend
from deckforge_core.modes.common import (
    LearnSummary,
    ModeError,
    list_packs,
    normalise_plan,
    pack_dir_for,
    packs_root,
    pptx_path,
    resolve_pack,
)
from deckforge_core.modes.critique import run_critique
from deckforge_core.modes.edit import EditResult, EditSpec, parse_edit, run_edit
from deckforge_core.modes.learn import run_learn
from deckforge_core.modes.make import MakeResult, run_make
from deckforge_core.modes.outline import OutlineLine, run_outline
from deckforge_core.modes.restyle import run_restyle

__all__ = [
    "BlendResult",
    "EditResult",
    "EditSpec",
    "LearnSummary",
    "MakeResult",
    "ModeError",
    "OutlineLine",
    "list_packs",
    "normalise_plan",
    "pack_dir_for",
    "packs_root",
    "parse_edit",
    "pptx_path",
    "resolve_pack",
    "run_blend",
    "run_critique",
    "run_edit",
    "run_learn",
    "run_make",
    "run_outline",
    "run_restyle",
]
