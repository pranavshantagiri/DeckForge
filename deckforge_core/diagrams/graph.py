"""Small helpers over the frozen GraphSpec contract (schemas/deck_plan.py).

Layout, render and the mermaid parser share this adjacency bookkeeping so each
file stays focused on its own concern. Pure python: no python-pptx imports here,
so these helpers run in plain unit tests.
"""

from __future__ import annotations

from collections import defaultdict, deque

from deckforge_core.schemas.deck_plan import GraphEdge, GraphNode, GraphSpec


def node_ids(spec: GraphSpec) -> list[str]:
    """Node ids in the spec's declaration order."""
    return [n.id for n in spec.nodes]


def node_by_id(spec: GraphSpec, node_id: str) -> GraphNode | None:
    for n in spec.nodes:
        if n.id == node_id:
            return n
    return None


def index_of(spec: GraphSpec) -> dict[str, int]:
    """Spec-order index per node id (stable tie-break key)."""
    return {n.id: i for i, n in enumerate(spec.nodes)}


def edges_from(spec: GraphSpec) -> list[GraphEdge]:
    return list(spec.edges)


def successors(spec: GraphSpec) -> dict[str, list[str]]:
    """dict[node_id] -> successors, keyed for every declared node."""
    adj: dict[str, list[str]] = defaultdict(list)
    for n in spec.nodes:
        adj[n.id]
    for e in spec.edges:
        if e.src in adj:
            adj[e.src].append(e.dst)
    return dict(adj)


def predecessors(spec: GraphSpec) -> dict[str, list[str]]:
    """dict[node_id] -> predecessors, keyed for every declared node."""
    adj: dict[str, list[str]] = defaultdict(list)
    for n in spec.nodes:
        adj[n.id]
    for e in spec.edges:
        if e.dst in adj:
            adj[e.dst].append(e.src)
    return dict(adj)


def is_acyclic(spec: GraphSpec) -> bool:
    """True when the graph has no directed cycle (Kahn's algorithm)."""
    pred = predecessors(spec)
    succ = successors(spec)
    ids = node_ids(spec)
    indeg = {nid: len(pred[nid]) for nid in ids}
    queue = deque(nid for nid in ids if indeg[nid] == 0)
    seen = 0
    while queue:
        u = queue.popleft()
        seen += 1
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return seen == len(ids)


def walk(spec: GraphSpec) -> list[str]:
    """BFS from sources (in-degree zero). Cycle members fall back to spec order
    behind the sources; deterministic for a given spec."""
    pred = predecessors(spec)
    succ = successors(spec)
    ids = node_ids(spec)
    seen: set[str] = set()
    order: list[str] = []
    queue = deque(nid for nid in ids if not pred[nid])
    queue.extend(nid for nid in ids if nid not in seen)
    while queue:
        u = queue.popleft()
        if u in seen:
            continue
        seen.add(u)
        order.append(u)
        for v in succ[u]:
            if v not in seen:
                queue.append(v)
    return order
