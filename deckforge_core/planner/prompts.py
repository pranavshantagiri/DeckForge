"""Prompts for planner (Workstream D)."""

from __future__ import annotations

from deckforge_core.schemas.deck_plan import DeckPlan
from deckforge_core.schemas.pack import FormatPack
from deckforge_core.schemas.slot_vocabulary import slots_for

SYSTEM_COPY_RULES = """COPY RULES:
- Use takeaway titles (e.g., "Churn fell 12%" not "Churn Update")
- Be specific and concrete
- Use short sentences
- No filler words
- No emoji bullets
- No rhetorical triplets
- Avoid repetition of sentence rhythm
- Never invent stats out of thin air (if facts not supplied, phrase as illustrative "e.g." or avoid)
"""


FORMAT_RULES = """FORMAT RULES:
- Fill ONLY the canonical slot names for each archetype (list them per archetype from slot_vocabulary)
- Never emit coordinates, colours, font sizes, or image URLs
- Deck is validated against a strict JSON schema
"""


def plan_system_message(pack: FormatPack, options: dict) -> str:
    rules = SYSTEM_COPY_RULES + "\n\n" + FORMAT_RULES

    # Add slot names per archetype
    slot_info = []
    # Get all archetypes in the pack or common ones
    try:
        archetypes = pack.archetype_list()
    except Exception:
        archetypes = []

    for arch in archetypes[:18]:  # limit
        try:
            names = slots_for(arch).names()
            slot_info.append(f"{arch}: {', '.join(names)}")
        except Exception:
            continue

    if slot_info:
        rules += "\n\nCANONICAL SLOTS PER ARCHETYPE:\n" + "\n".join(slot_info)

    return rules


def plan_user_message(prompt: str, options: dict) -> str:
    audience = options.get("audience", "") if options else ""
    tone = options.get("tone", "professional") if options else "professional"
    slide_count = options.get("slide_count", 10) if options else 10

    msg = f"PROMPT: {prompt}\n\n"
    msg += f"AUDIENCE: {audience}\n"
    msg += f"TONE: {tone}\n"
    msg += f"SLIDE_COUNT: {slide_count}\n"
    return msg


# Few-shot example
FEW_SHOT_EXAMPLE = DeckPlan.model_validate(
    {
        "title": "Example Deck",
        "aspect_ratio": "16:9",
        "created_by": "template-planner",
        "pack": "demo",
        "slides": [
            {
                "n": 1,
                "archetype": "title",
                "title": "Product adoption gains traction",
                "slots": {
                    "kicker": {"text": " "},
                    "title": {"text": "Product adoption gains traction"},
                    "subtitle": {"text": "Professional update"},
                },
            },
            {
                "n": 2,
                "archetype": "agenda",
                "title": "Agenda",
                "slots": {
                    "items": {"items": ["Context", "Evidence", "Recommendation"]},
                },
            },
            {
                "n": 3,
                "archetype": "big-number",
                "title": "Adoption rose 40% in six months",
                "slots": {
                    "number": {"text": "40%"},
                    "caption": {"text": "increase in active users"},
                },
            },
        ],
    }
)
