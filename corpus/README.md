# Sample corpus

A corpus of `.pptx` decks drives development and golden tests.

- `scripts/generate_corpus.py` — deterministic **synthetic corpus generator**
  (30+ decks, varied archetypes and style profiles, known ground truth). This is
  the default, CI-safe path (see DECISION D004).
- `scripts/fetch_corpus.py` — optional fetcher for a small set of permissively
  licensed real decks (Wikimedia Commons etc.). Requires explicit opt-in.

Raw/downloaded files are git-ignored (`corpus/raw/`, `.download-cache/`).