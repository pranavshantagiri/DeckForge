"""Model layer for the DeckForge desktop GUI.

Everything the interface needs that is not a widget lives here: pack discovery,
pack learning, deck planning + rendering, slide previews and QA summaries.
Deliberately Qt-free so the whole flow can be exercised headless.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from deckforge_core.analysis import analyse_decks, learn_pack
from deckforge_core.config import Settings, data_dir, ensure_dirs
from deckforge_core.ingest.parser import extract_directory
from deckforge_core.logging_util import get_logger
from deckforge_core.planner import (
    PlannerOptions,
    TemplatePlanner,
    last_warnings,
    plan_deck,
)
from deckforge_core.providers.registry_bootstrap import (
    available_llm_names,
    bootstrap_providers,
)
from deckforge_core.providers.render import RenderBackend, RendererAutodetect
from deckforge_core.qa import run_qa
from deckforge_core.renderer.engine import render_deck
from deckforge_core.renderer.pack_io import list_packs, load_dfpack, load_pack
from deckforge_core.schemas.blueprints import BlueprintLibrary
from deckforge_core.schemas.deck_plan import DeckPlan
from deckforge_core.schemas.pack import FormatPack
from deckforge_core.schemas.qa import QASummaryReport

log = get_logger("deckforge.gui.models")

# ``(percent, message)``; percent < 0 means "still working, fraction unknown".
ProgressFn = Callable[[int, str], None]

ASPECT_RATIOS = ("16:9", "4:3", "16:10", "portrait")
TONES = ("professional", "conversational", "technical", "executive", "friendly")

_SECRET_PROVIDERS = ("anthropic", "openai", "gemini", "local")


def _emit(progress: Optional[ProgressFn], percent: int, message: str) -> None:
    if progress is not None:
        progress(percent, message)


# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #
def packs_root(packs_dir: Optional[Path] = None) -> Path:
    if packs_dir is not None:
        return Path(packs_dir)
    return ensure_dirs()["packs"]


def decks_root(decks_dir: Optional[Path] = None) -> Path:
    root = Path(decks_dir) if decks_dir is not None else ensure_dirs()["decks"]
    root.mkdir(parents=True, exist_ok=True)
    return root


def settings_file(settings: Settings) -> Path:
    """Where a :class:`Settings` instance persists; the class keeps it private."""
    path = getattr(settings, "_path", None)
    if path is not None:
        return Path(path)
    return data_dir() / Settings.FILE_NAME


def slugify(text: str, fallback: str = "deck") -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip()).strip("-").lower()
    return slug or fallback


def new_deck_dir(title: str, decks_dir: Optional[Path] = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return decks_root(decks_dir) / f"{slugify(title)}-{stamp}"


def decks_in(folder: Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    found = {path for path in folder.glob("*.pptx")} | {
        path for path in folder.glob("**/*.pptx")
    }
    return sorted(path for path in found if path.is_file())


# --------------------------------------------------------------------------- #
# Packs
# --------------------------------------------------------------------------- #
@dataclass
class PackEntry:
    """One row of the packs home screen."""

    name: str
    path: Path
    pack_name: str = ""
    deck_count: int = 0
    slide_count: int = 0
    archetype_count: int = 0
    aspect_ratios: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    error: str = ""

    @property
    def usable(self) -> bool:
        return not self.error

    @property
    def summary(self) -> str:
        if self.error:
            return f"unreadable: {self.error}"
        ratios = ", ".join(self.aspect_ratios) or "unknown"
        parts = [
            f"{self.deck_count} decks",
            f"{self.slide_count} slides",
            f"{self.archetype_count} archetypes",
            ratios,
        ]
        head = f"{self.pack_name} · " if self.pack_name and self.pack_name != self.name else ""
        return head + " · ".join(parts)


def list_pack_entries(packs_dir: Optional[Path] = None) -> list[PackEntry]:
    root = packs_root(packs_dir)
    entries: list[PackEntry] = []
    for name in list_packs(root):
        entry = PackEntry(name=name, path=root / name)
        try:
            pack, _library = load_pack(entry.path)
        except Exception as exc:
            log.warning("pack %s unreadable: %s", entry.path, exc)
            entry.error = str(exc)
        else:
            entry.pack_name = pack.name
            entry.deck_count = pack.source_deck_count
            entry.slide_count = pack.source_slide_count
            entry.archetype_count = len(pack.archetypes)
            entry.aspect_ratios = list(pack.aspect_ratios)
            entry.created_at = pack.created_at
        entries.append(entry)
    return entries


def load_pack_from_dir(pack_dir: Path) -> tuple[FormatPack, BlueprintLibrary]:
    return load_pack(Path(pack_dir))


def import_pack_zip(
    zip_path: Path, packs_dir: Optional[Path] = None
) -> PackEntry:
    """Unpack a ``.dfpack`` into the packs folder and return its row."""
    source = Path(zip_path)
    root = packs_root(packs_dir)
    name = source.stem.removesuffix(".dfpack") or source.stem
    pack_dir = root / slugify(name, fallback="pack")
    counter = 2
    while (pack_dir / "pack.json").exists():
        pack_dir = root / f"{slugify(name, fallback='pack')}-{counter}"
        counter += 1
    pack, _library = load_dfpack(source, pack_dir)
    return PackEntry(
        name=pack.name,
        path=pack_dir,
        pack_name=pack.name,
        deck_count=pack.source_deck_count,
        slide_count=pack.source_slide_count,
        archetype_count=len(pack.archetypes),
        aspect_ratios=list(pack.aspect_ratios),
        created_at=pack.created_at,
    )


@dataclass
class LearnPackResult:
    pack: FormatPack
    pack_dir: Path
    deck_count: int
    slide_count: int
    archetypes: list[str]
    aspect_ratios: list[str]
    new_archetypes: list[str]
    ingest_errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"{self.deck_count} decks, {self.slide_count} slides, "
            f"{len(self.archetypes)} archetypes"
        )


def learn_pack_from_folder(
    folder: Path,
    name: str,
    *,
    target_dir: Optional[Path] = None,
    progress: Optional[ProgressFn] = None,
    use_cache: bool = True,
    max_decks: int = 0,
    db_path: Optional[Path] = None,
) -> LearnPackResult:
    """Scan ``folder`` for .pptx decks and build a saved Format Pack in the GUI.

    The folder is ingested first so the progress bar tracks real work and the
    analysis report is available for the summary, then :func:`learn_pack` builds
    the blueprints and writes the pack. ``db_path`` isolates the ingest cache of
    the analysis pass; the pack build pass always shares the app cache, so pass
    ``use_cache=False`` to keep a run fully inside a temporary directory.
    """
    source = Path(folder)
    files = decks_in(source)
    if not files:
        raise ValueError(f"no .pptx decks found in {source}")

    pack_name = (name or "").strip() or source.name
    pack_dir = Path(target_dir) if target_dir else packs_root() / slugify(pack_name)
    total = len(files)
    _emit(progress, 5, f"Scanning {total} deck(s) in {source.name}")

    seen = {"n": 0}

    def _on_file(path: Path) -> None:
        seen["n"] += 1
        _emit(
            progress,
            5 + int(30 * seen["n"] / total),
            f"Reading {seen['n']}/{total}: {path.name}",
        )

    ingested = extract_directory(
        source, use_cache=use_cache, on_progress=_on_file, db_path=db_path
    )
    usable = [deck for deck in ingested.decks if deck.slides]
    if not usable:
        raise ValueError(f"no readable decks in {source}")

    _emit(progress, 40, f"Analysing {len(usable)} deck(s)")
    report = analyse_decks(usable)

    _emit(progress, 70, f"Building pack '{pack_name}'")
    pack = learn_pack(
        source,
        pack_name,
        target_dir=pack_dir,
        use_cache=use_cache,
        max_decks=max_decks,
    )
    _emit(progress, 95, f"Saving pack to {pack_dir}")

    return LearnPackResult(
        pack=pack,
        pack_dir=pack_dir,
        deck_count=pack.source_deck_count,
        slide_count=pack.source_slide_count,
        archetypes=list(pack.archetypes),
        aspect_ratios=list(pack.aspect_ratios),
        new_archetypes=list(report.new_archetypes),
        ingest_errors=[f"{item.path.name}: {item.message}" for item in ingested.errors],
    )


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
@dataclass
class GenerationRequest:
    pack_dir: Path
    brief: str
    slide_count: int = 10
    tone: str = "professional"
    audience: str = ""
    aspect_ratio: str = "16:9"
    use_llm: bool = False
    llm_provider: str = ""
    render_backend: str = RenderBackend.AUTO.value
    out_dir: Optional[Path] = None
    file_name: str = ""

    def options(self) -> PlannerOptions:
        return PlannerOptions(
            slide_count=max(3, int(self.slide_count)),
            tone=self.tone,
            audience=self.audience,
            aspect_ratio=self.aspect_ratio,
        )

    def target_pptx(self) -> Path:
        out_dir = Path(self.out_dir) if self.out_dir else new_deck_dir(self.brief)
        name = slugify(self.file_name or self.brief)
        return out_dir / f"{name}.pptx"


@dataclass
class SlidePreview:
    number: int
    archetype: str
    title: str
    image_path: str = ""
    error: str = ""
    issues: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        heading = self.title or self.archetype
        return f"{self.number}. {heading}"


@dataclass
class GenerationResult:
    pptx_path: Path
    plan: DeckPlan
    previews: list[SlidePreview]
    warnings: list[str] = field(default_factory=list)
    backend: str = RenderBackend.NONE.value
    qa: Optional[QASummaryReport] = None

    @property
    def slide_count(self) -> int:
        return len(self.plan.slides)

    @property
    def rendered_previews(self) -> int:
        return sum(1 for preview in self.previews if preview.image_path)

    @property
    def errors_total(self) -> int:
        return self.qa.errors_total() if self.qa else 0

    @property
    def warnings_total(self) -> int:
        return self.qa.warnings_total() if self.qa else 0


def available_render_backends() -> list[str]:
    return [backend.value for backend in RendererAutodetect().available]


def available_llm_providers() -> list[str]:
    bootstrap_providers()
    return available_llm_names()


def secret_providers() -> tuple[str, ...]:
    return _SECRET_PROVIDERS


def build_plan(
    request: GenerationRequest,
    pack: FormatPack,
    *,
    settings: Optional[Settings] = None,
) -> DeckPlan:
    """Plan ``request`` either with the offline template planner or the LLM."""
    if request.use_llm:
        return plan_deck(
            request.brief,
            pack,
            options=request.options(),
            settings=settings,
            llm_provider=request.llm_provider or None,
        )
    return TemplatePlanner().plan(request.brief, pack, request.options())


def render_slide_previews(
    pptx_path: Path,
    out_dir: Path,
    backend: str,
) -> tuple[str, dict[int, str], list[str]]:
    """Render slide PNGs with the best available backend.

    Returns ``(backend_used, image paths by slide number, notes)``. A machine
    without PowerPoint or LibreOffice simply gets no images: the GUI falls back
    to a text card per slide.
    """
    notes: list[str] = []
    images: dict[int, str] = {}
    if backend == RenderBackend.NONE.value:
        return backend, images, ["slide previews disabled (renderer set to none)"]

    try:
        renderer = RendererAutodetect().resolve(backend)
    except Exception as exc:
        notes.append(f"renderer {backend!r} unavailable: {exc}")
        return RenderBackend.NONE.value, images, notes

    if renderer.backend == RenderBackend.NONE:
        notes.append("no slide renderer installed (PowerPoint or LibreOffice)")
        return RenderBackend.NONE.value, images, notes

    try:
        rendered = renderer.render(Path(pptx_path), Path(out_dir))
    except Exception as exc:  # pragma: no cover - renderers swallow their own errors
        notes.append(f"slide render failed: {exc}")
        return renderer.backend.value, images, notes

    for slide in rendered:
        if slide.image_path and Path(slide.image_path).is_file():
            images[slide.number] = slide.image_path
        elif slide.error:
            notes.append(f"slide {slide.number}: {slide.error}")
    return renderer.backend.value, images, notes


def generate(
    request: GenerationRequest,
    *,
    progress: Optional[ProgressFn] = None,
    settings: Optional[Settings] = None,
    run_checks: bool = True,
) -> GenerationResult:
    """Plan, render and preview a deck from a saved pack. Offline by default."""
    if not (request.brief or "").strip():
        raise ValueError("a deck brief is required")

    _emit(progress, 5, f"Loading pack {Path(request.pack_dir).name}")
    pack, library = load_pack_from_dir(request.pack_dir)

    _emit(progress, 20, "Planning deck")
    plan = build_plan(request, pack, settings=settings)
    warnings: list[str] = list(last_warnings)

    pptx_path = request.target_pptx()
    _emit(progress, 45, f"Rendering {len(plan.slides)} slides")
    rendered = render_deck(plan, pack, library, pptx_path, warnings=warnings)

    render_dir = rendered.out_path.parent / "renders"
    _emit(progress, 65, "Rendering slide previews")
    backend, images, notes = render_slide_previews(
        rendered.out_path, render_dir, request.render_backend
    )
    warnings.extend(notes)

    qa_report: Optional[QASummaryReport] = None
    if run_checks:
        _emit(progress, 88, "Running QA checks")
        qa_report = run_qa(
            plan,
            pack,
            library,
            render_backend=RenderBackend.NONE.value,
            out_dir=rendered.out_path.parent,
        )
        warnings.extend(qa_report.qa_log)

    by_number: dict[int, list[str]] = {}
    if qa_report is not None:
        for result in qa_report.slides:
            by_number[result.slide_n] = [issue.message for issue in result.issues]

    previews = [
        SlidePreview(
            number=slide.n,
            archetype=slide.archetype,
            title=slide.title or "",
            image_path=images.get(slide.n, ""),
            issues=by_number.get(slide.n, []),
        )
        for slide in plan.slides
    ]

    _emit(progress, 100, f"Saved {rendered.out_path.name}")
    return GenerationResult(
        pptx_path=rendered.out_path,
        plan=plan,
        previews=previews,
        warnings=warnings,
        backend=backend,
        qa=qa_report,
    )


# --------------------------------------------------------------------------- #
# Desktop integration
# --------------------------------------------------------------------------- #
def open_in_default_app(path: Path) -> str:
    """Hand a file to the OS default handler (PowerPoint for .pptx)."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"{target} does not exist")
    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        startfile(str(target))
        return str(target)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)])
    return str(target)


def reveal_in_file_manager(path: Path) -> str:
    """Show a file in Explorer/Finder with the containing folder open."""
    target = Path(path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist")
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(target)])
    else:
        folder = target.parent if target.is_file() else target
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(folder)])
    return str(target)
