# Workstream B — Learn a Pack (Archetype & Style Analysis)

`learn_pack` turns a folder of `.pptx` decks into a `FormatPack`: a reusable
style profile plus one `Blueprint` per slide archetype found.

## Pipeline

```
learn_pack(folder, name, *, target_dir, use_cache=True, max_decks=0)
  └─ extract_directory()            # Workstream A ingest (cached/re-parsed)
  └─ analyse_decks()                # detection + clustering + style
  └─ blueprints_from_slides()       # per-archetype slot geometry
  └─ save_pack(pack, library, target_dir)  # Workstream C persistence
```

- `deckforge_core/analysis/archetype.py` — deterministic rule-based detection.
  Rules run in priority order over the `ExtractedSlide` geometry:

  1. `full-bleed-image` — a picture covering ≥ 85% of both dimensions,
     hugging the slide bounds.
  2. `big-number` — a run ≥ 32 pt whose text is numeric / a percentage.
  3. `title` — ≤ 3 text shapes, exactly one ≥ 30 pt, the rest ≤ 18 pt and
     short; no chart/table/substantial picture.
  4. `section-divider` — ≤ 4 shapes, one ≥ 24 pt, others ≤ 18 pt, few words.
  5. `quote` — text that opens and closes with quote marks.
  6. `chart` / 7. `table` — parsed chart / table content on the slide.
  8. `statement` — ≤ 4 shapes, ≤ 25 words, one run ≥ 22 pt.
  9. `closing` — closing keywords (thanks / contact / questions) with ≤ 3
     short shapes.
  10. layout group: `image-left` / `image-right` (picture ≥ 18% x 22% of the
      canvas on one side), `three-cards` (three equal, evenly-spaced boxes in
      one row), `comparison` (two equal-width columns each with a heading),
      `two-column-text`, `agenda`, `timeline`, `process-flow`, `team`.
  11. Fallback `two-column-text` at low confidence.

  Pure-text rules are skipped when a substantial picture is present so
  image layouts are never misread as titles or statements. Quote slides are
  skipped by `section-divider` (a quoted line is a quote, not a divider).

- `deckforge_core/analysis/cluster.py` — KMeans over slide feature vectors
  (size/length/density stats, `FEATURE_DIM=13`), silhouette to pick `k`, and
  `discover_archetypes()` to surface new/unseen clusters. Detection labels
  are used to name clusters; anything without a canonical vocabulary is
  recorded as a new archetype rather than blueprint-ed.

- `deckforge_core/analysis/style_profile.py` — `style_from_decks()`
  - Fonts: modal family of the per-slide largest run → `heading`; modal of
    all runs → `body`.
  - Palette: collects `fill_hex` + run `color_hex` weights; ≤ 3 distinct
    colours used directly, otherwise usage-weighted KMeans (k=5) centroids.
    Roles are derived from darkness/brightness: darkest = text, brightest
    well-used = bg, second-darkest = muted-text, remainder by usage become
    accents/neutrals. Degrades to a neutral 6-role palette when no explicit
    colours survive ingestion.
  - Margins/grid: modal edge distances of content shapes; 12-column grid
    with baseline from body-height shapes.
  - Type scale: modal run sizes within tiers (body = overall mode, h1 = most
    common run ≥ 20 pt, etc.).

- `deckforge_core/analysis/blueprint.py` — `blueprints_from_slides()` maps
  the representative slide's shapes to the canonical slot vocabulary
  (`schemas/slot_vocabulary.py`), snapping regions to a 0.01 grid.
  Text `TextLimits` come from 5th–95th percentiles of real usage across the
  archetype group; `min/max_words_total` from the group's totals. Columnar
  layouts get a stacked `portrait` `AlternateArrangement`.

- `deckforge_core/analysis/build_pack.py` — orchestrates the above; writes
  `pack.json`, `style_profile.json` and `blueprints/<archetype>.json` via
  `renderer.pack_io.save_pack` (`load_pack` round-trips).

## Public API

`deckforge_core/analysis/__init__.py` exports `learn_pack`, `analyse_decks`
(`AnalysisReport` with `archetype_counts`, `clusters`, `new_archetypes`,
aspect ratios and the derived `StyleProfile`), `detect_archetype`,
`style_from_decks`, the cluster/discovery helpers and `slide_features`.

## Corpora, determinism & known limitations

- Fully deterministic: KMeans uses `random_state=0`; `learn_pack` run twice
  over the same folder yields identical pack style and archetype sets.
- The shipped `corpus/raw/` decks are minimal skeletons (kicker + title on
  every slide, no images/charts/tables), so structural detection on that
  corpus alone yields only `title` and `section-divider`. Run `learn_pack`
  over richer .pptx inputs to learn the layout archetypes.
- Ingest colour extraction is currently disabled in this environment: the
  installed python-pptx exposes `RGBColor` as a tuple, so Workstream A's
  `int(rgb)` cast raises and `color_hex`/`fill_hex` are always `None`. The
  style profile degrades to a neutral palette and records the gap in
  `notes`.

## Tests

`tests/test_archetype.py`, `tests/test_style_profile.py`,
`tests/test_blueprint.py` and `tests/test_learn_pack.py` cover detection on
hand-built slides, profile derivation from explicitly styled decks,
blueprint geometry/vocabulary/portrait alternates, and the end-to-end
`learn_pack` + `load_pack` round-trip on a mixed python-pptx corpus
(`pytest.skip` falls back gracefully when `corpus/raw` is empty).