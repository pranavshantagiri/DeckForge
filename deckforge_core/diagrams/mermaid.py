"""A Mermaid flowchart-subset parser → GraphSpec.

Supported syntax (documented subset)
-----------------------------------
* Headers: ``graph TD`` / ``graph TB`` / ``graph LR`` / ``flowchart TD`` /
  ``flowchart LR``. ``TB`` is treated like ``TD``; other directions (RL, BT)
  raise :class:`DiagramError`. A mermaid source without a header defaults to
  ``TD``.
* Nodes:
  * ``A``                      → process, label ``A``
  * ``A[Some label]``          → process with an explicit label
  * ``A["Label with spaces"]`` → quoted label
  * ``A((circle))``            → terminal: ``start`` (no incoming edge) or ``end``
  * ``A{decision}``            → decision
* Edges: ``-->`` (directed), ``---`` (undirected — flags the whole graph as
  undirected), ``-.->`` (kept as ``style="dashed"``), ``-->|label|`` (edge
  label). ``A --> B --> C`` chains work.
* ``%%`` comments and blank lines are skipped.

Subgraphs
---------
``subgraph …/end`` delimiters are recognised and skipped; members are flattened
into the same graph. Mermaid grouping has no home in GraphSpec, so the grouping
is intentionally lost (documented trade-off).

Anything outside this subset raises :class:`DiagramError` instead of guessing.
"""

from __future__ import annotations

import re

from deckforge_core.diagrams import DiagramError
from deckforge_core.schemas.deck_plan import GraphEdge, GraphNode, GraphSpec

_DIR_RE = re.compile(r"^\s*(graph|flowchart)\s+([A-Za-z0-9]+)\s*$")
_EDGE_RE = re.compile(r"(-\.->|-->|---)")
_EDGE_LABEL_RE = re.compile(r"^\s*\|([^|]*)\|")
_SHAPE_RE = re.compile(r"^([A-Za-z_][\w-]*)(.*)$", re.DOTALL)
_CIRCLE = "(("


def parse_mermaid(src: str) -> tuple[GraphSpec, str]:
    """Parse the supported Mermaid subset; returns ``(GraphSpec, orientation)``."""
    if src is None or not src.strip():
        raise DiagramError("empty mermaid source")
    statements = [ln.strip() for ln in src.splitlines()]
    statements = [ln for ln in statements if ln and not ln.startswith("%%")]

    orientation = "TD"
    if statements and _DIR_RE.match(statements[0]):
        direction = _DIR_RE.match(statements[0]).group(2).upper()
        if direction in ("TD", "TB"):
            orientation = "TD"
        elif direction == "LR":
            orientation = "LR"
        else:
            raise DiagramError(f"unsupported mermaid direction {direction!r} (only TD/TB/LR)")
        statements = statements[1:]

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    circles: set[str] = set()
    has_undirected = False

    def store(token: str) -> GraphNode:
        nid, label, kind, shaped = _parse_node_token(token)
        if nid in nodes:
            old = nodes[nid]
            if shaped:
                old.label = label
                old.kind = kind
            if shaped and kind != _CIRCLE:
                circles.discard(nid)
            return old
        node = GraphNode(id=nid, label=label, kind=kind)
        nodes[nid] = node
        if shaped and kind == _CIRCLE:
            circles.add(nid)
        return node

    for line in statements:
        if line.startswith("subgraph") or line == "end":
            continue
        parts = _EDGE_RE.split(line)
        tokens = parts[::2]
        ops = parts[1::2]
        if not tokens or not tokens[0].strip():
            raise DiagramError(f"line has no node: {line!r}")
        prev_id = store(tokens[0]).id
        for i, op in enumerate(ops):
            chunk = tokens[i + 1]
            edge_label: str | None = None
            label_match = _EDGE_LABEL_RE.match(chunk)
            if label_match:
                edge_label = label_match.group(1)
                chunk = chunk[label_match.end() :].strip()
            if not chunk:
                raise DiagramError(f"edge {op!r} is missing a target node")
            if op == "---":
                has_undirected = True
            style = "dashed" if op == "-.->" else None
            dst_id = store(chunk).id
            edges.append(GraphEdge(src=prev_id, dst=dst_id, label=edge_label, style=style))
            prev_id = dst_id

    targets = {e.dst for e in edges}
    for nid in circles:
        nodes[nid].kind = "end" if nid in targets else "start"

    return GraphSpec(directed=not has_undirected, nodes=list(nodes.values()), edges=edges), orientation


# --------------------------------------------------------------------------- #
# Token parsing
# --------------------------------------------------------------------------- #
def _parse_node_token(token: str) -> tuple[str, str, str, bool]:
    """Return (id, label, kind, shaped). ``shaped`` is True when the token
    carried an explicit shape (so a later mention can override a plain one)."""
    token = token.strip()
    match = _SHAPE_RE.match(token)
    if not match:
        raise DiagramError(f"unrecognised node syntax: {token!r}")
    nid, rest = match.group(1), match.group(2).strip()
    if not rest:
        return nid, nid, "process", False
    if rest.startswith("[") and rest.endswith("]"):
        return nid, _clean_label(rest[1:-1]), "process", True
    if rest.startswith("{") and rest.endswith("}"):
        return nid, _clean_label(rest[1:-1]), "decision", True
    if rest.startswith("((") and rest.endswith("))"):
        return nid, _clean_label(rest[2:-2]), _CIRCLE, True
    raise DiagramError(f"unsupported node syntax: {token!r}")


def _clean_label(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text
