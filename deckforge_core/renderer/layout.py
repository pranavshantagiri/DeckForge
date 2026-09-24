"""Map blueprint slot defs onto a Canvas: relative fractions -> absolute EMU.

Decision (documented): blueprints define absolute fractional regions of the
FULL slide — they were learned from real slides that way. Globally applying
:class:`StyleProfile.margins` on top of already-scaled fraction regions would
move content off the intended design, so margins are NOT applied to slot
geometry here. Margins are honoured only as internal insets of text frames
(see engine), which keeps text off the box edges without distorting geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from deckforge_core.renderer.canvas import Canvas, relative_to_emu
from deckforge_core.schemas.blueprints import SlotDef
from deckforge_core.schemas.deck_plan import SlidePlan


@dataclass(frozen=True)
class PlacedSlot:
    """A blueprint :class:`SlotDef` resolved to absolute EMU coordinates."""

    name: str
    slot_def: SlotDef
    left: int
    top: int
    width: int
    height: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.width, self.height


def layout_slots(
    plan: SlidePlan, slots: List[SlotDef], canvas: Canvas
) -> List[PlacedSlot]:
    """Convert every effective slot def into a :class:`PlacedSlot`.

    ``plan`` is accepted for interface symmetry with the renderer; only the
    ``slots`` and ``canvas`` drive the geometry.
    """
    placements: List[PlacedSlot] = []
    for slot in slots:
        placements.append(
            PlacedSlot(
                name=slot.name,
                slot_def=slot,
                left=relative_to_emu(slot.region.x, canvas.width_emu),
                top=relative_to_emu(slot.region.y, canvas.height_emu),
                width=max(1, relative_to_emu(slot.region.w, canvas.width_emu)),
                height=max(1, relative_to_emu(slot.region.h, canvas.height_emu)),
            )
        )
    return placements
