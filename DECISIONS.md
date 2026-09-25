# Decision Log

Every deviation from, or clarification of, the spec is recorded here with a
reason. If a technology decision changes, it changes here first.

## D001 — Python version: 3.13 on this machine, `requires-python >= 3.12`
The spec named Python 3.12. The build machine has Python 3.13.7. The codebase
targets 3.12+ syntax/behaviour (no 3.13-only features), `pyproject.toml` sets
`requires-python = ">=3.12"`, and CI runs 3.12. Reason: 3.13 works and is
strictly newer; nothing in the dep tree pins 3.12.

## D002 — Primary slide renderer: PowerPoint COM; LibreOffice is the fallback
Detected on the dev machine: `POWERPNT.EXE` (Office 16) present, LibreOffice
absent. `RendererAutodetect` prefers COM, then LibreOffice, then NONE (graceful
degradation with per-slide error entries). Reason: COM gives the truest
rendering and is the most common human install on Windows.

## D003 — Privacy default: `local_only = true`
DeckForge starts with zero network calls. Generating in local-only mode uses the
deterministic planner (heuristic/template) until the user opts in per-pack to
"share slide images/text with the AI" — which enumerates exactly what will be
sent. Reason: "local-only mode makes zero network calls (verified by test)" is a
hard acceptance criterion, and ingestion must stay local by default.

## D004 — Sample corpus is *generated*, with an optional real-deck fetcher
Acceptance says "at least 30 sample decks ... generated or downloaded from
permissively licensed sources". We build a deterministic **synthetic corpus
generator** (30+ archetype-varied decks with known ground truth) so CI can run
golden-file tests offline and cheaply; `tools/fetch_corpus.py` supplements
with a small number of permissively-licensed real decks (Wikimedia Commons etc.)
when a developer opts in. Reason: reproducibility for golden tests beats a
thousand stale downloaded decks; avoids licensing landmines in the repo.

## D005 — Formats on disk
A Format Pack folder contains `pack.json`, `style_profile.json`, `blueprints/`,
`theme/`, `examples/`, `index/`. Geometry in blueprints is always relative
(0..1) fractions of slide width/height. A `.dfpack` (Phase 1J) is a zip of that
folder plus a manifest. Reason: matches section 4 of the spec exactly.

## D006 — Pack archetype vocabulary is closed at contract level, extensible
The 18 archetypes in `schemas/archetypes.py` are the v1 vocabulary. During Learn,
unknown discovered patterns become *new* archetype values in a pack's blueprint
set (never ad-hoc strings in the planner). Reason: planner must only emit
archetypes a pack can render.

## D007 — `deckforge_core` has zero UI deps; GUI is an optional extra
Core pulls Typer/rich already (CLI is the reference interface to build and test
first). `PySide6` is `[project.optional-dependencies] gui`. Reason: spec
"packaged as a library with no UI dependencies", and PySide6 is heavy for the
headless ingest path.

## D008 — LLM structured output: prompt-for-JSON with reparsing fallback
The reference `LLMProvider.complete_structured` wraps completion in a strict-JSON
system prompt and reparses with the offending output fed back on failure.
Native tool/structured APIs are provider-specific overrides where available.
Reason: portable across Anthropic/OpenAI/Gemini/local without SDK variance.

## D009 — Cost accounting is per-call, in SQLite
Every completion records input/output/cache tokens + computed USD cost into
`llm_usage`. Prices are per-provider constants in the provider class (defaults
modified when registrations land in Phase 1D). Reason: acceptance asks for
cost/token accounting; SQLite keeps it queryable and GUI-displayable.

## D010 — Plan then verify: workstreams only write files they own
Subagents own specific paths (see PROGRESS.md). Anything outside that list must
be flagged to the orchestrator before being touched. Reason: prevents contract
drift mid-integration.

## D011 — CI workflow file is staged locally, not tracked, until token has scope
The GitHub token of this machine lacks the `workflow` scope, so GitHub rejects
pushes containing `.github/workflows/ci.yml`. The file lives on disk and is
git-ignored. To activate: run `gh auth refresh -h github.com -s workflow`, then
remove the ignore rule, `git add .github/workflows/ci.yml`, commit, push.
Reason: blocked push is worse than a temporarily-unpushed CI file.

## D012 — Canonical slot vocabulary is orchestrator-owned
`deckforge_core/schemas/slot_vocabulary.py` defines exactly which slot names the
planner may fill per archetype and which ContentKinds each accepts. Renderer
blueprints map these names to geometry; unknown slot names in a plan are ignored
with a QA warning. This file is the D↔C contract and must only change with an
officially recorded schema bump. Reason: planner and renderer run in parallel
and must agree on slot names without talking.