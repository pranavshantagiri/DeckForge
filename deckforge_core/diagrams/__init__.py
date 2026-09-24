"""Native-shape diagrams (Sugiyama-lite layout, native PPTX connectors).

Public API
----------
* :class:`layout_graph` — layered layout of a :class:`GraphSpec` inside a
  :class:`SlotRegion`, pure python (no Graphviz).
* :func:`parse_mermaid` — Mermaid flowchart subset → ``(GraphSpec, orientation)``.
* :func:`render_diagram` — draw a :class:`DiagramSpec` onto a python-pptx slide
  as real AutoShapes + connectors.
* :class:`DiagramError` — raised for unsupported/unparseable diagram input.
"""

from __future__ import annotations

from deckforge_core.errors import DeckForgeError


class DiagramError(DeckForgeError):
    """Invalid or unsupported diagram input (mermaid syntax, orientation…)."""


from deckforge_core.diagrams.graph import (  # noqa: E402  (after DiagramError on purpose)
    edges_from,
    index_of,
    is_acyclic,
    node_by_id,
    node_ids,
    predecessors,
    successors,
    walk,
)
from deckforge_core.diagrams.layout import (  # noqa: E402
    ORIENTATION_LR,
    ORIENTATION_TD,
    Layout,
    PlacedEdge,
    PlacedNode,
    layout_graph,
)
from deckforge_core.diagrams.mermaid import parse_mermaid  # noqa: E402
from deckforge_core.diagrams.render import DiagramInfo, render_diagram  # noqa: E402

__all__ = [
    "DiagramError",
    "DiagramInfo",
    "Layout",
    "ORIENTATION_LR",
    "ORIENTATION_TD",
    "PlacedEdge",
    "PlacedNode",
    "edges_from",
    "index_of",
    "is_acyclic",
    "layout_graph",
    "node_by_id",
    "node_ids",
    "parse_mermaid",
    "predecessors",
    "render_diagram",
    "successors",
    "walk",
]
