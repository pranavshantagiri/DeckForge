"""Layered (Sugiyama-lite) layout for GraphSpec, pure python (no Graphviz).

The layout produces *relative* coordinates (fractions of slide width/height)
inside a ``SlotRegion`` — exactly what the renderer needs.

Algorithm
---------
1. **Layering** — longest-path layering from the sources (nodes with no
   in-edges). Cycles are handled by a bounded relaxation: at most N passes for
   N nodes, so a cyclic graph always terminates. Afterwards any edge that would
   still not point strictly downward (a broken back-edge) has its **target
   pushed one layer later**. The result: every edge runs top-to-bottom (TD) or
   left-to-right (LR) with no exceptions, and cycle graphs never loop forever.
2. **Ordering within a layer** — a single barycenter sweep from the first
   layer. Each node's preferred position is the *mean* of its predecessors'
   positions in the previous layer; ties fall back to declaration order.
3. **Positioning** — layers become horizontal bands (TD) / vertical columns
   (LR) across the region; members are distributed along the perpendicular
   axis and centred in their band. Node size scales with label length and is
   clamped so a whole layer always fits. Manual ``GraphNode.x/.y`` overrides
   (slide-relative, interpreted as the node's centre) take precedence over the
   computed centre and are clamped to stay inside the region.

Edges are routed **elbow style** (down/across/down for TD) with the bend at the
vertical midpoint between the two boxes; an edge staying within the same layer
(rare, only from broken feedback) falls back to a straight side-to-side
connector.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deckforge_core.diagrams import DiagramError
from deckforge_core.diagrams.graph import index_of, node_ids, predecessors, successors
from deckforge_core.schemas.blueprints import SlotRegion
from deckforge_core.schemas.deck_plan import GraphSpec

ORIENTATION_TD = "TD"
ORIENTATION_LR = "LR"


@dataclass
class PlacedNode:
    """A positioned node. ``x``/``y``/``w``/``h`` are slide-relative (0..1)
    fractions of width/height; ``x``/``y`` are the top-left corner."""

    id: str
    label: str
    x: float
    y: float
    w: float
    h: float
    kind: str = "process"


@dataclass
class PlacedEdge:
    """A routed edge. ``route`` is an ordered list of (x, y) slide-relative
    points; consecutive points are drawn as straight connector segments."""

    src: str
    dst: str
    route: list[tuple[float, float]]
    label: str | None = None
    style: str | None = None
    directed: bool = True


@dataclass
class Layout:
    nodes: list[PlacedNode] = field(default_factory=list)
    edges: list[PlacedEdge] = field(default_factory=list)
    layers: list[list[str]] = field(default_factory=list)
    broken_edges: list[tuple[str, str]] = field(default_factory=list)
    overlaps: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def layout_graph(
    spec: GraphSpec,
    region: SlotRegion,
    *,
    directed: bool,
    orientation: str = ORIENTATION_TD,
) -> Layout:
    """Lay out ``spec`` inside ``region``; see the module docstring."""
    if orientation not in (ORIENTATION_TD, ORIENTATION_LR):
        raise DiagramError(
            f"unknown orientation {orientation!r}; expected {ORIENTATION_TD!r} or {ORIENTATION_LR!r}"
        )
    ids = node_ids(spec)
    succ = successors(spec)
    pred = predecessors(spec)
    idx = index_of(spec)

    warnings: list[str] = []
    if not ids:
        warnings.append("graph has no nodes; layout is empty")

    layer, broken = _assign_layers(ids, succ)
    groups = _group_layers(ids, layer)
    ordered = _order_layers(groups, pred, idx)
    placed = _place(ordered, {n.id: n for n in spec.nodes}, region, orientation)
    _ensure_within_region(placed, region, warnings)

    if broken:
        warnings.append(
            f"broke {len(broken)} back-edge(s) by pushing their targets to a later layer"
        )
    edges, missing = _route_edges(spec, placed, layer, orientation, directed)
    for unknown in missing:
        warnings.append(f"edge references unknown node {unknown!r}; skipped")

    overlaps = _overlaps(placed)
    for a, b in overlaps:
        warnings.append(f"node overlap: {a!r} × {b!r}")

    return Layout(
        nodes=placed,
        edges=edges,
        layers=ordered,
        broken_edges=broken,
        overlaps=overlaps,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Layering + ordering
# --------------------------------------------------------------------------- #
def _assign_layers(ids: list[str], succ: dict[str, list[str]]) -> tuple[dict[str, int], list[tuple[str, str]]]:
    """Longest-path layering. See module docstring; bounded and idempotent."""
    n = max(1, len(ids))
    layer = {i: 0 for i in ids}
    for _ in range(n):
        changed = False
        for u in ids:
            lu = layer[u]
            for v in succ[u]:
                if layer[v] < lu + 1:
                    layer[v] = lu + 1
                    changed = True
        if not changed:
            break
    broken: list[tuple[str, str]] = []
    for u in ids:
        for v in succ[u]:
            if layer[v] < layer[u] + 1:
                layer[v] = layer[u] + 1
                broken.append((u, v))
    return layer, broken


def _group_layers(ids: list[str], layer: dict[str, int]) -> list[list[str]]:
    if not ids:
        return []
    mx = max(layer.values())
    groups: list[list[str]] = [[] for _ in range(mx + 1)]
    for nid in ids:
        groups[layer[nid]].append(nid)
    return groups


def _order_layers(layers: list[list[str]], pred: dict[str, list[str]], idx: dict[str, int]) -> list[list[str]]:
    """One sweep of barycenter ordering from the first layer."""
    if not layers:
        return []
    ordered: list[list[str]] = [list(layers[0])]
    order = {nid: i for i, nid in enumerate(layers[0])}
    for members in layers[1:]:
        scored = []
        for nid in members:
            positions = [order.get(p, idx.get(p, 0)) for p in pred.get(nid, [])]
            score = sum(positions) / len(positions) if positions else idx.get(nid, 0)
            scored.append((nid, score))
        scored.sort(key=lambda item: (item[1], idx.get(item[0], 0)))
        row = [nid for nid, _ in scored]
        ordered.append(row)
        order = {nid: i for i, nid in enumerate(row)}
    return ordered


# --------------------------------------------------------------------------- #
# Positioning
# --------------------------------------------------------------------------- #
def _default_width(label: str) -> float:
    """Node width heuristic: 0.12..0.24 slide-width fraction by label length."""
    return min(max(0.12 + 0.008 * len(label), 0.12), 0.24)


def _clamp(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        return (lo + hi) / 2
    return min(max(value, lo), hi)


def _place(
    layers: list[list[str]],
    spec_by_id: dict[str, object],
    region: SlotRegion,
    orientation: str,
) -> list[PlacedNode]:
    placed: list[PlacedNode] = []
    n_layers = max(1, len(layers))
    for ci, members in enumerate(layers):
        m = max(1, len(members))
        for mi, nid in enumerate(members):
            node = spec_by_id.get(nid)
            label = getattr(node, "label", None) or nid
            kind = getattr(node, "kind", None) or "process"
            if orientation == ORIENTATION_TD:
                w_max = max(region.w / m * 0.9, 0.01)
                h_max = max(region.h / n_layers * 0.9, 0.01)
            else:
                w_max = max(region.w / n_layers * 0.9, 0.01)
                h_max = max(region.h / m * 0.9, 0.01)
            w = min(_default_width(label), w_max)
            h = min(max(0.06, 0.14 * region.h), h_max)
            if orientation == ORIENTATION_TD:
                cx = region.x + region.w * (mi + 0.5) / m
                cy = region.y + region.h * (ci + 0.5) / n_layers
            else:
                cx = region.x + region.w * (ci + 0.5) / n_layers
                cy = region.y + region.h * (mi + 0.5) / m
            cx = _clamp(cx, region.x + w / 2, region.x + region.w - w / 2)
            cy = _clamp(cy, region.y + h / 2, region.y + region.h - h / 2)
            if getattr(node, "x", None) is not None:
                cx = _clamp(node.x, region.x + w / 2, region.x + region.w - w / 2)
            if getattr(node, "y", None) is not None:
                cy = _clamp(node.y, region.y + h / 2, region.y + region.h - h / 2)
            placed.append(
                PlacedNode(id=nid, label=label, x=cx - w / 2, y=cy - h / 2, w=w, h=h, kind=kind)
            )
    return placed


def _ensure_within_region(placed: list[PlacedNode], region: SlotRegion, warnings: list[str]) -> None:
    for pn in placed:
        nx = _clamp(pn.x, region.x, region.x + region.w - pn.w)
        ny = _clamp(pn.y, region.y, region.y + region.h - pn.h)
        if abs(nx - pn.x) > 1e-9 or abs(ny - pn.y) > 1e-9:
            pn.x, pn.y = nx, ny
            warnings.append(f"node {pn.id!r} clamped to fit its region")


def _overlaps(placed: list[PlacedNode]) -> list[tuple[str, str]]:
    """Pairs whose rects intersect by more than 5% of the smaller node."""
    out: list[tuple[str, str]] = []
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            a, b = placed[i], placed[j]
            ix = max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
            iy = max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
            inter = ix * iy
            if inter <= 0:
                continue
            if inter > 0.05 * min(a.w * a.h, b.w * b.h):
                out.append((a.id, b.id))
    return out


# --------------------------------------------------------------------------- #
# Edge routing
# --------------------------------------------------------------------------- #
def _route_edges(
    spec: GraphSpec,
    placed: list[PlacedNode],
    layer_of: dict[str, int],
    orientation: str,
    directed: bool,
) -> tuple[list[PlacedEdge], list[str]]:
    by_id = {pn.id: pn for pn in placed}
    out: list[PlacedEdge] = []
    missing: list[str] = []
    for e in spec.edges:
        u = by_id.get(e.src)
        v = by_id.get(e.dst)
        if u is None or v is None:
            missing.append(e.dst if u is None else e.src)
            continue
        if layer_of.get(e.src, 0) < layer_of.get(e.dst, 0):
            if orientation == ORIENTATION_TD:
                p0 = (u.x + u.w / 2, u.y + u.h)
                mid_y = (u.y + u.h + v.y) / 2
                route = [p0, (p0[0], mid_y), (v.x + v.w / 2, mid_y), (v.x + v.w / 2, v.y)]
            else:
                p0 = (u.x + u.w, u.y + u.h / 2)
                mid_x = (u.x + u.w + v.x) / 2
                route = [p0, (mid_x, p0[1]), (mid_x, v.y + v.h / 2), (v.x, v.y + v.h / 2)]
        elif orientation == ORIENTATION_TD:
            route = [(u.x + u.w, u.y + u.h / 2), (v.x, v.y + v.h / 2)]
        else:
            route = [(u.x + u.w / 2, u.y + u.h), (v.x + v.w / 2, v.y)]
        out.append(
            PlacedEdge(src=e.src, dst=e.dst, route=route, label=e.label, style=e.style, directed=directed)
        )
    return out, missing
