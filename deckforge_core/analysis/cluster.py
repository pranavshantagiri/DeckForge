"""Clustering + discovery of unknown archetypes (Workstream B).

Slides are embedded as fixed-length feature vectors (:mod:`features`) and
grouped with KMeans. The best ``k`` is chosen by maximal average silhouette
over ``k = 2..min(12, N//4)`` so the pack builder can discover layout families
that the heuristic classifier alone does not name.

Discovered clusters that are *not* dominated by one of the canonical 18
archetypes are flagged as "new"; v1 only records their suggested names (they do
not get a canonical vocabulary entry yet).
"""

from __future__ import annotations

import warnings
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

from deckforge_core.analysis.archetype import detect_archetype
from deckforge_core.analysis.features import FEATURE_DIM, slide_features

_MIN_CLUSTERS = 2
_MAX_CLUSTERS = 12
_KM_RANDOM_STATE = 0

#: The canonical archetype names any discovered cluster is compared against.
CANONICAL_ARCHETYPES: frozenset[str] = frozenset(
    {
        "title",
        "section-divider",
        "agenda",
        "statement",
        "big-number",
        "two-column-text",
        "image-left",
        "image-right",
        "full-bleed-image",
        "three-cards",
        "comparison",
        "timeline",
        "process-flow",
        "chart",
        "table",
        "team",
        "quote",
        "closing",
    }
)


@dataclass
class DiscoveredCluster:
    """One cluster found by :func:`cluster_slides` + :func:`discover_archetypes`."""

    label: int
    size: int
    representative_slide_index: int
    dominant_heuristic_archetype: str
    is_new: bool
    confidence: float = field(default=0.0)
    suggested_names: list[str] = field(default_factory=list)


def embed_slides(slides) -> np.ndarray:
    """Return an ``(N, FEATURE_DIM)`` feature matrix for ``slides``."""
    if not slides:
        return np.zeros((0, FEATURE_DIM), dtype=float)
    return np.vstack([slide_features(s) for s in slides])


def _max_k(n_samples: int) -> int:
    return max(_MIN_CLUSTERS, min(_MAX_CLUSTERS, n_samples // 4))


def cluster_slides(
    vectors: np.ndarray, n_clusters: int | None = None
) -> tuple[np.ndarray, int]:
    """Cluster ``vectors`` with KMeans (``random_state=0``).

    ``n_clusters`` overrides the automatic choice. When None, the k in
    ``2..min(12, N//4)`` with the best average silhouette wins; degenerate
    inputs (0/1 samples, identical vectors, too-few samples for k=2) collapse
    to a single cluster labelled ``0``.
    """
    vectors = np.asarray(vectors, dtype=float)
    n = vectors.shape[0]
    if n == 0:
        raise ValueError("cannot cluster an empty matrix")
    unique = len(np.unique(vectors, axis=0))
    if n < 4 or unique < 4:
        return np.zeros(n, dtype=int), 1

    if n_clusters is not None:
        return _fit(vectors, n_clusters)

    best_k = 1
    best_labels = np.zeros(n, dtype=int)
    best_score = -1.0
    with warnings.catch_warnings():
        # Spare corpora with duplicated feature vectors routinely yield fewer
        # distinct clusters than k; that is expected, not an error.
        warnings.simplefilter("ignore", ConvergenceWarning)
        for k in range(_MIN_CLUSTERS, min(_max_k(n), unique) + 1):
            try:
                labels, _ = _fit(vectors, k)
            except ValueError:
                continue
            if len(set(labels.tolist())) < 2:
                continue
            if k > n - 1:
                break
            try:
                score = silhouette_score(vectors, labels)
            except ValueError:
                continue
            if score > best_score:
                best_score, best_k, best_labels = score, k, labels
    if best_k == 1:
        best_labels = np.zeros(n, dtype=int)
    return best_labels, best_k


def _fit(vectors: np.ndarray, k: int):
    model = KMeans(n_clusters=k, random_state=_KM_RANDOM_STATE, n_init=10)
    labels = model.fit_predict(vectors)
    return labels, model


def discover_archetypes(slides, labels: np.ndarray) -> list[DiscoveredCluster]:
    """Characterise each cluster via the heuristic classifier and geometry.

    ``representative_slide_index`` is the slide closest to that cluster's
    centroid; ``is_new`` is True when the dominant heuristically-detected
    archetype is not among the canonical 18; ``suggested_names`` stays empty in
    v1 (integration only records clusters).
    """
    labels = np.asarray(labels, dtype=int)
    clusters: list[DiscoveredCluster] = []
    vectors = embed_slides(slides)
    centroids: dict[int, np.ndarray] = {}
    if len(vectors):
        for k in sorted(set(labels.tolist())):
            member = vectors[labels == k]
            centroids[k] = member.mean(axis=0)

    for k in sorted(set(labels.tolist())):
        indices = np.where(labels == k)[0]
        counts: Counter[str] = Counter()
        for i in indices:
            arch, _ = detect_archetype(slides[i])
            counts[arch] += 1
        dominant, freq = counts.most_common(1)[0]
        confidence = freq / len(indices)

        rep_index = int(indices[0])
        if k in centroids:
            distances = np.linalg.norm(vectors[indices] - centroids[k], axis=1)
            rep_index = int(indices[int(np.argmin(distances))])

        clusters.append(
            DiscoveredCluster(
                label=int(k),
                size=int(len(indices)),
                representative_slide_index=rep_index,
                dominant_heuristic_archetype=dominant,
                is_new=dominant not in CANONICAL_ARCHETYPES,
                confidence=float(confidence),
                suggested_names=[],
            )
        )
    return clusters
