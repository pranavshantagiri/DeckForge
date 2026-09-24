"""Pure layout tests: layering, ordering, sizing, overlap and manual overrides.

No python-pptx involved — these exercise the geometry contract only.
"""

from __future__ import annotations

import pytest

from deckforge_core.diagrams import ORIENTATION_LR, layout_graph
from deckforge_core.schemas.blueprints import SlotRegion
from deckforge_core.schemas.deck_plan import GraphEdge, GraphNode, GraphSpec

REGION = SlotRegion(x=0.05, y=0.05, w=0.9, h=0.9)


def _chain_branch_spec() -> GraphSpec:
    return GraphSpec(
        directed=True,
        nodes=[GraphNode(id=n) for n in "ABCDEFG"],
        edges=[
            GraphEdge(src=s, dst=d)
            for s, d in [("A", "B"), ("B", "C"), ("C", "D"), ("E", "F"), ("F", "G"), ("B", "F")]
        ],
    )


def _assert_inside_region(lay) -> None:
    for pn in lay.nodes:
        assert pn.x >= REGION.x - 1e-9
        assert pn.y >= REGION.y - 1e-9
        assert pn.x + pn.w <= REGION.x + REGION.w + 1e-9
        assert pn.y + pn.h <= REGION.y + REGION.h + 1e-9


def test_layer_counts_and_no_overlap():
    lay = layout_graph(_chain_branch_spec(), REGION, directed=True)
    assert [sorted(row) for row in lay.layers] == [
        ["A", "E"],
        ["B"],
        ["C", "F"],
        ["D", "G"],
    ]
    assert lay.overlaps == []
    assert not lay.broken_edges
    assert len(lay.edges) == 6
    _assert_inside_region(lay)


def test_cycle_terminates():
    spec = GraphSpec(
        directed=True,
        nodes=[GraphNode(id="A"), GraphNode(id="B")],
        edges=[GraphEdge(src="A", dst="B"), GraphEdge(src="B", dst="A")],
    )
    lay = layout_graph(spec, REGION, directed=True)
    assert len(lay.nodes) == 2
    assert len(lay.edges) == 2
    assert lay.broken_edges  # at least one back-edge had to be pushed later
    assert lay.overlaps == []
    _assert_inside_region(lay)


def test_manual_overrides_respected():
    spec = GraphSpec(
        directed=True,
        nodes=[GraphNode(id="A"), GraphNode(id="D", x=0.62, y=0.5)],
        edges=[GraphEdge(src="A", dst="D")],
    )
    lay = layout_graph(spec, REGION, directed=True)
    d = next(pn for pn in lay.nodes if pn.id == "D")
    assert d.x + d.w / 2 == pytest.approx(0.62, abs=0.001)
    assert d.y + d.h / 2 == pytest.approx(0.5, abs=0.001)


def test_edge_route_is_elbow_td():
    lay = layout_graph(_chain_branch_spec(), REGION, directed=True)
    ab = next(e for e in lay.edges if e.src == "A" and e.dst == "B")
    assert len(ab.route) == 4  # down, across, down
    from_b = [e for e in lay.edges if e.src == "B"]
    assert len(from_b) == 2
    # both of B's edges leave from the same bottom-centre point
    assert len({e.route[0] for e in from_b}) == 1


def test_lr_orientation_mirrors_geometry():
    lay = layout_graph(_chain_branch_spec(), REGION, directed=True, orientation=ORIENTATION_LR)
    assert [sorted(row) for row in lay.layers] == [
        ["A", "E"],
        ["B"],
        ["C", "F"],
        ["D", "G"],
    ]
    assert lay.overlaps == []
    _assert_inside_region(lay)


def test_directed_flag_propagates_to_edges():
    spec = GraphSpec(
        directed=False,
        nodes=[GraphNode(id="A"), GraphNode(id="B")],
        edges=[GraphEdge(src="A", dst="B")],
    )
    lay = layout_graph(spec, REGION, directed=False)
    assert lay.edges[0].directed is False


def test_empty_graph_is_harmless():
    lay = layout_graph(GraphSpec(nodes=[]), REGION, directed=True)
    assert lay.nodes == []
    assert lay.edges == []
    assert any("no nodes" in w for w in lay.warnings)
