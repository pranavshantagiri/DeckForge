# Sample corpus

A corpus of `.pptx` decks drives development and golden tests.

- `scripts/generate_corpus.py` — deterministic **synthetic corpus generator**
  (30+ decks, varied archetypes and style profiles, known ground truth). This is
  the default, CI-safe path (see DECISION D004).
- `tools/fetch_corpus.py` — optional fetcher for a small set of permissively
  licensed real decks (Apache POI regression fixtures). Requires explicit opt-in.

Raw/downloaded files are git-ignored (`corpus/raw/`, `corpus/external/`,
`.download-cache/`).