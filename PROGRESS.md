# Progress

Updated live by the orchestrator. Legend: ✅ done · 🔄 in progress · ⬜ waiting
for dependency · 🔴 blocked · ✖ cancelled

## Phase 0 — Contracts (orchestrator)

| Item | Status |
| --- | --- |
| Env checks (python 3.13, git, PowerPoint COM, no LibreOffice) | ✅ |
| Repo scaffold, `pyproject.toml`, module layout, `.gitignore` | ✅ |
| Data contracts: schemas (pack, style profile, blueprints, deck plan, QA) | ✅ |
| Provider interfaces: LLM, images, slide renderer + registry | ✅ |
| Storage: SQLite metadata schema + settings/secret separation | ✅ |
| CLI skeleton (`version`/`about`) | ✅ |
| Tests: contracts, providers, storage, config, CLI — all passing | ✅ |
| Docs: README, DECISIONS, PROGRESS, QA_REPORT | ✅ |
| Git init + Phase 0 commit | ✅ |
| Push to github.com/pranavshantagiri/DeckForge (main) | ✅ |
| Canonical slot vocabulary (D↔C contract) | ✅ |

## Phase 1 — Workstreams (parallel)

| Workstream | Owner | Depends on | Status |
| --- | --- | --- | --- |
| A. Ingest & Parse | ingest/ | schemas | ✅ done — parser, cache, thumbnails, deterministic corpus generator (36-deck sample, 18/18 archetypes detected) |
| B. Archetype & Style Analysis | analysis/ | A output schema | ✅ done — archetype detector (18 archetypes), blueprint slots, KMeans style profile, learn_pack |
| C. Renderer | renderer/ | schemas | ✅ done — canvas, layout, textfit, charts, tables, engine, pack_io |
| D. AI Planner | planner/ + providers.llm | schemas | ✅ done — prompts, pricing, lint, slide/plan planner; Anthropic/Gemini/OpenAI/local providers |
| E. Images | images/ + providers.images | schemas | ✅ done — local library, remote providers, attribution, dhash/rank, registry bootstrap |
| F. Diagrams | diagrams/ | schemas (GraphSpec) | ✅ done — layered layout, native shapes/connectors, Mermaid subset |
| G. Theme | theme/ | schemas (StyleProfile) | ✅ done — contrast, fonts, brief→profile, theme XML builder |
| H. QA Loop | qa/ + providers.render | C renderer | ✅ done — checks, autofix, subprocess-COM renderer, vision scoring |
| I. GUI | gui/ | CLI + core API | ✅ done — PySide6 app (packs, generate+preview, settings), offscreen-safe tests; `deckforge-gui` entry |
| J. Packaging & Tests | packaging/ + tools/ | C, H | ✅ done — PyInstaller one-dir CLI build verified, Inno Setup script (iscc unavailable locally), offline Apache POI corpus fetcher, 7-test golden e2e (offline, deterministic) |

## Phase 2 — Integration

| Item | Status |
| --- | --- |
| Wire Learn → Pack → Generate end-to-end on sample corpus | ✅ `learn corpus/raw --pack demo` → `make/outline`, offline deterministic |
| Modes package (`deckforge_core/modes/`): learn, make, outline, restyle, critique, blend, edit, packs, settings | ✅ |
| Full CLI surface (all modes + `packs`/`settings`/`provider` subcommands) | ✅ |
| Slot-normalisation bridge (plan ↔ learned blueprint slots, no silent content loss) | ✅ merged `*_heading`→`*_body`, dropped-unknown notes surfaced |
| `DECKFORGE_DATA_DIR` override for test/portable isolation | ✅ |
| Restyle, Outline, Critique, Blend, Edit-slide working CLI | ✅ modes are GUI-shareable `run_*` functions |
| Aspect-ratio switching (16:9 / 4:3 / portrait) | 🔄 CLI `--aspect` + blueprint alternates exist; portrait not yet verified |
| Full test suite before declaring phase done | ✅ 319 passed / 3 skipped, ruff clean |

## Phase 3 — Polish & hardening

| Item | Status |
| --- | --- |
| Performance: ingest ~500 decks with multiprocessing | ⬜ |
| Error handling + logging polish, first-run experience | ⬜ |
| PyInstaller + Inno Setup build, installer smoke test | ⬜ |
| Blind-style review + `QA_REPORT.md` findings | ⬜ |