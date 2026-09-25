# DeckForge

A Windows desktop tool that makes **human-looking PowerPoint decks**.

DeckForge learns a presentation format from hundreds of real `.pptx` files,
distils them into a reusable **Format Pack**, then uses a prompt to craft a new
deck in that format. Nothing is "trained". The AI only plans content and picks
archetypes; a deterministic renderer builds real, native, editable slides.

- Output is **native editable .pptx** — real text boxes, shapes, charts, tables
  and connectors. Slides are never flattened to images.
- Style comes **only from the pack**: palette, fonts, type scale, grid, margins,
  image treatment. The planner never emits colours, coordinates or sizes.
- **Multi-provider AI** — Anthropic default, pluggable OpenAI / Gemini / local.
- Real photography by default (Unsplash / Pexels / your local library), AI image
  generation optional and off.
- Native-shape **flowcharts** and native **charts** with editable data.
- **Visual QA** — renders every slide and auto-fixes overflow, overlap, contrast
  and off-grid issues (up to 3 iterations).
- **Privacy-first**: ingestion is fully local by default. Sending slide images or
  text to any API requires an explicit, visible opt-in per pack ("local-only"
  mode skips every cloud call).

## Repository layout

```
deckforge_core/            # library (no UI dependencies)
  schemas/                 # data contracts (pack, blueprints, deck plan, QA)
  providers/               # interfaces: LLM, images, render (COM / LibreOffice)
  ingest/                  # extract shapes/styles/geometry from .pptx
  analysis/                # archetype + style analysis, clustering, blueprints
  renderer/                # Deck Plan + Format Pack -> native .pptx
  planner/                 # outline + slot filling prompts, lint, costs
  images/                  # real-photo providers, local index
  diagrams/                # native-shape flowcharts (Sugiyama layout)
  theme/                   # PowerPoint theme/master generation
  qa/                      # render, deterministic checks, vision review, autofix
  modes/                   # Learn, Generate, Restyle, Critique, Blend, Edit
  cli/                     # Typer interface
  gui/                     # PySide6 desktop interface (Phase 1I)
  storage/                 # SQLite metadata, vector store location
tests/                     # pytest + golden-file tests
tools/                     # corpus generation + fetch (also scripts-style tools)
packaging/                 # PyInstaller spec + Inno Setup script + build wrapper
```

## Reference implementation status

| Area | Status |
| --- | --- |
| Data contracts (schemas + provider interfaces) | done (Phase 0) |
| Ingest & Parse | Phase 1A |
| Archetype & Style Analysis | Phase 1B |
| Renderer | Phase 1C |
| AI Planner | Phase 1D |
| Images | Phase 1E |
| Diagrams | Phase 1F |
| Theme generation | Phase 1G |
| Visual QA | Phase 1H |
| GUI | Phase 1I |
| Packaging & installer | Phase 1J |

Tracked live in [PROGRESS.md](PROGRESS.md).

## Install for development

Requires Python 3.12+ (`py` launcher recommended on Windows).

```powershell
git clone <repo> DeckForge
cd DeckForge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,anthropic,gui,win]"
deckforge version
pytest
```

## Usage (CLI)

```powershell
# Learn a pack from a folder of decks
deckforge learn "C:\decks" --pack demo

# Generate a deck
deckforge make "Q3 results for the board" --pack demo --slides 10

# Restyle an existing deck into a pack's format
deckforge restyle "old.pptx" --pack demo --out new.pptx

# Outline only (narrative, no design)
deckforge outline "Product launch" --pack demo --out outline.md

# Critique a deck against a pack
deckforge critique "deck.pptx" --pack demo

# Blend two packs
deckforge blend --layout packA --palette packB --out packC

# Edit a single slide without touching the rest
deckforge edit "deck.pptx" --slide 4 --prompt "shorten this"
```

Every mode also has a GUI screen (run `deckforge-gui`).

## Privacy & keys

- API keys go to the **Windows Credential Manager** (keyring), never to config
  files or logs.
- `local_only` is on by default. While it is on, DeckForge makes **zero network
  calls** (a test enforces this).
- Per-pack opt-in: when you enable "share slides / text with the AI" for a pack,
  DeckForge says exactly what will be sent (thumbnails, extracted text) before
  anything leaves the machine.

## Rendering slides to images (for QA/previews)

Auto-detected: PowerPoint COM first (truest rendering, needs PowerPoint
installed), then LibreOffice headless. With neither installed, DeckForge still
builds decks but skips image QA with a clear message.

## Anti-AI-look rules

Encoded in the renderer, the planner prompts and the QA checks — see the spec
table in [DECISIONS.md](DECISIONS.md). Highlights: one dominant + 1-2 accents; two
fonts only; sentence-case takeaway titles ("Churn fell 12%", not "Churn Update");
no filler phrases (banned-phrase list + post-generation lint); real photos with
consistent treatment; native diagrams; deliberate archetype variety.

## Architecture

```
 prompt ──> Planner (LLM) ──> DeckPlan ──┐
        FormatPack ──────────────────────┼──> Renderer ──> .pptx ──> QA loop ──> deck.pptx + QA report
        (style + blueprints)             │      (deterministic)
 Existing decks ──> Learn ──> FormatPack ┘      charts/tables/diagrams/images
```