"""Mermaid-subset parser tests: shapes, edges, styles, orientation, errors."""

from __future__ import annotations

import pytest

from deckforge_core.diagrams import DiagramError, parse_mermaid


def test_chain_parses_to_process_nodes():
    graph, orientation = parse_mermaid("graph TD\n  A --> B --> C\n  B --> D")
    assert orientation == "TD"
    assert len(graph.nodes) == 4
    assert len(graph.edges) == 3
    assert graph.directed is True
    assert all(n.kind == "process" for n in graph.nodes)


def test_decision_named_edges_and_terminals():
    graph, _ = parse_mermaid("flowchart TD\n S((start)) --> A{Is it?}\n A -->|yes| E((done))")
    by = {n.id: n for n in graph.nodes}
    assert by["A"].kind == "decision"
    assert by["A"].label == "Is it?"
    assert by["S"].kind == "start"
    assert by["E"].kind == "end"
    yes_edge = next(e for e in graph.edges if e.src == "A")
    assert yes_edge.label == "yes"


def test_dashed_edge_keeps_style():
    graph, _ = parse_mermaid("graph TD\n  A -.-> B")
    assert graph.edges[0].style == "dashed"
    assert graph.directed is True


def test_lr_orientation_returned():
    _, orientation = parse_mermaid("flowchart LR\n  A --> B")
    assert orientation == "LR"


def test_undirected_edges_flag_graph_undirected():
    graph, _ = parse_mermaid("graph TD\n  A --- B")
    assert graph.directed is False


def test_quoted_labels():
    graph, _ = parse_mermaid('graph TD\n  A["Label with spaces"] --> B')
    assert {n.id: n for n in graph.nodes}["A"].label == "Label with spaces"


def test_tb_treated_as_td():
    _, orientation = parse_mermaid("graph TB\n  A --> B")
    assert orientation == "TD"


def test_subgraph_members_flattened():
    graph, _ = parse_mermaid("graph TD\n  subgraph one\n    A --> B\n  end\n  B --> C")
    assert {n.id for n in graph.nodes} == {"A", "B", "C"}
    assert len(graph.edges) == 2


def test_comments_skipped():
    graph, _ = parse_mermaid("%% header comment\ngraph TD\n  %% another comment\n  A --> B")
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_invalid_link_syntax_raises():
    with pytest.raises(DiagramError):
        parse_mermaid("graph TD\n  A --o B")


def test_unhandled_direction_raises():
    with pytest.raises(DiagramError):
        parse_mermaid("flowchart BT\n  A --> B")


def test_empty_source_raises():
    with pytest.raises(DiagramError):
        parse_mermaid("   \n  ")
