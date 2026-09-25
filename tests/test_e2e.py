"""Golden end-to-end test: corpus -> learn -> pack on disk -> plan -> render.

This is the one test that drives *every* workstream through a single real run:

    generate_corpus (A) -> extract_directory (A) -> analyse_decks/learn_pack (B)
    -> save_pack/load_pack (C) -> TemplatePlanner (D) -> render_deck (C)
    -> run_qa (H) -> extract_deck (A) on the rendered .pptx

Everything is offline and hermetic on purpose:

* no network - the corpus is generated, never downloaded (``fetch_corpus.py`` is
  only probed through its non-network CLI paths),
* no LLM - the deterministic :class:`TemplatePlanner` does the planning,
* no live COM - PowerPoint is never launched; QA runs with ``render_backend="none"``
  so only the deterministic checks execute,
* single-threaded, and the ingest cache is bypassed (``use_cache=False``) so no
  state leaks into ``%APPDATA%`` between runs.

It also pins the reproducibility guarantee end to end: the same seed must
produce byte-identical corpus decks, byte-identical pack artefacts and a
byte-identical rendered .pptx.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from deckforge_core.analysis import analyse_decks, learn_pack
from deckforge_core.ingest import extract_deck, extract_directory
from deckforge_core.planner.planner import PlannerOptions, TemplatePlanner
from deckforge_core.qa import QACheckType, run_qa
from deckforge_core.renderer import load_pack, render_deck
from deckforge_core.schemas.blueprints import BlueprintLibrary
from deckforge_core.schemas.deck_plan import (
    ChartSeries,
    ChartSpec,
    DeckPlan,
    SlidePlan,
    SlotValue,
    TableSpec,
)
from deckforge_core.schemas.pack import FormatPack
from deckforge_core.tools import generate_corpus as gc

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_CORPUS = REPO_ROOT / "tools" / "fetch_corpus.py"

CORPUS_SEED = 20240316
CORPUS_DECKS = 12
SLIDES_PER_DECK = 13
PROMPT = "DeckForge end to end: learn a format pack, then render a deck"
GOLDEN_ARCHETYPES = ("title", "big-number", "chart", "table", "quote")


# --------------------------------------------------------------------------- #
# Fixtures: one corpus + one learned pack for the whole module
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("e2e-corpus") / "raw"
    assert gc.main(
        ["--out", str(out), "--decks", str(CORPUS_DECKS), "--seed", str(CORPUS_SEED)]
    ) == 0
    return out


@pytest.fixture(scope="module")
def learned(corpus_dir: Path, tmp_path_factory):
    """The explicit learn pipeline, then the pack reloaded from disk."""
    pack_dir = tmp_path_factory.mktemp("e2e-pack")
    extracted = extract_directory(corpus_dir, use_cache=False)
    report = analyse_decks(extracted.decks)
    pack = learn_pack(corpus_dir, "e2e", target_dir=pack_dir, use_cache=False)
    reloaded, library = load_pack(pack_dir)
    return {
        "dir": pack_dir,
        "pack": reloaded,
        "library": library,
        "report": report,
        "learned": pack,
        "decks": extracted.decks,
        "errors": extracted.errors,
    }


def _slide_texts(slide) -> list[str]:
    return [p.text() for shape in slide.shapes for p in shape.text if p.text()]


def _golden_plan(pack: FormatPack) -> DeckPlan:
    """A hand-built, fully deterministic plan: one slide per archetype, native
    chart and table payloads, and speaker notes on three of the five slides."""
    return DeckPlan(
        title="DeckForge end to end",
        subtitle="learned from real decks, rendered natively",
        audience="the board",
        aspect_ratio="16:9",
        pack=pack.name,
        created_by="e2e-golden",
        slides=[
            SlidePlan(
                n=1,
                archetype="title",
                title="DeckForge end to end",
                slots={
                    "kicker": SlotValue(text="Q3 2026"),
                    "title": SlotValue(text="DeckForge end to end"),
                    "subtitle": SlotValue(
                        text="learned from real decks, rendered natively"
                    ),
                },
                speaker_notes="Frame the run: learn a pack, then render a deck.",
            ),
            SlidePlan(
                n=2,
                archetype="big-number",
                title="Twelve decks became one pack",
                slots={
                    "number": SlotValue(number="12"),
                    "caption": SlotValue(text="decks analysed into the pack"),
                    "source": SlotValue(text="Source: internal analytics"),
                },
                speaker_notes="Twelve decks, one pack, every archetype covered.",
            ),
            SlidePlan(
                n=3,
                archetype="chart",
                title="Revenue by quarter",
                slots={
                    "title": SlotValue(text="Revenue by quarter"),
                    "chart": SlotValue(
                        chart=ChartSpec(
                            chart_type="column",
                            categories=["Q1", "Q2", "Q3", "Q4"],
                            series=[
                                ChartSeries(name="Plan", values=[1.0, 1.2, 1.4, 1.6])
                            ],
                            show_legend=False,
                        )
                    ),
                    "source": SlotValue(text="Source: finance"),
                },
                speaker_notes="The plan line is flat; the actual is not.",
            ),
            SlidePlan(
                n=4,
                archetype="table",
                title="Quarterly metrics",
                slots={
                    "title": SlotValue(text="Quarterly metrics"),
                    "table": SlotValue(
                        table=TableSpec(
                            columns=["Metric", "Actual", "Plan"],
                            rows=[
                                ["Revenue", "$4.2M", "$3.9M"],
                                ["NPS", "91", "85"],
                            ],
                        )
                    ),
                    "source": SlotValue(text="Source: board pack"),
                },
            ),
            SlidePlan(
                n=5,
                archetype="quote",
                title="Why packs",
                slots={
                    "quote": SlotValue(text="A plan without an owner is a wish list."),
                    "attribution": SlotValue(text="- the operating committee"),
                },
                speaker_notes="Close on operating discipline.",
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Learn: corpus -> extracted decks -> report -> pack directory -> reload
# --------------------------------------------------------------------------- #
def test_learn_pipeline_extracts_analyses_and_persists(learned, corpus_dir: Path) -> None:
    assert len(list(corpus_dir.glob("*.pptx"))) == CORPUS_DECKS
    assert len(learned["decks"]) == CORPUS_DECKS
    assert learned["errors"] == []

    report = learned["report"]
    assert report.deck_count == CORPUS_DECKS
    assert report.slide_count == CORPUS_DECKS * SLIDES_PER_DECK
    assert report.aspect_ratios == ["16:9"]
    assert len(report.archetype_counts) >= 12
    for archetype in ("title", "section-divider", "big-number", "chart", "table"):
        assert report.archetype_counts.get(archetype), report.archetype_counts

    pack_dir: Path = learned["dir"]
    assert (pack_dir / "pack.json").is_file()
    assert (pack_dir / "style_profile.json").is_file()
    assert (pack_dir / "manifest.json").is_file()
    assert len(list((pack_dir / "blueprints").glob("*.json"))) >= 12

    pack: FormatPack = learned["pack"]
    assert pack.name == "e2e"
    assert pack.source_deck_count == CORPUS_DECKS
    assert pack.created_at is not None
    assert set(pack.aspect_ratios) == {"16:9"}
    # the explicitly-run analysis and learn_pack must agree
    assert pack.archetypes == learned["learned"].archetypes
    assert pack.style == report.style

    library: BlueprintLibrary = learned["library"]
    assert set(GOLDEN_ARCHETYPES) <= set(library.archetypes())
    assert set(library.archetypes()) <= set(pack.archetypes)


def test_learned_packs_style_is_usable(learned) -> None:
    style = learned["pack"].style
    assert style.fonts.heading and style.fonts.body
    assert style.palette.has("text") and style.palette.has("bg")
    assert style.palette.hex("text") != style.palette.hex("bg")
    names = {entry.name for entry in style.type_scale.entries}
    assert {"h1", "body", "kicker", "caption", "big-number"} <= names
    assert 0.0 <= style.confidence.overall <= 1.0


# --------------------------------------------------------------------------- #
# Plan + render: the real offline planner path
# --------------------------------------------------------------------------- #
def test_offline_planner_renders_every_planned_slide(learned, tmp_path: Path) -> None:
    pack: FormatPack = learned["pack"]
    library: BlueprintLibrary = learned["library"]

    plan = TemplatePlanner().plan(
        PROMPT, pack, PlannerOptions(slide_count=6, tone="technical", audience="the board")
    )
    assert len(plan.slides) == 6
    assert plan.pack == pack.name
    assert plan.aspect_ratio in pack.aspect_ratios
    assert [s.n for s in plan.slides] == [1, 2, 3, 4, 5, 6]
    planned_archetypes = {s.archetype for s in plan.slides}
    assert len(planned_archetypes) >= 4
    # the planner may only ask for archetypes the learned pack can actually draw
    assert planned_archetypes <= set(library.archetypes()), sorted(planned_archetypes)

    warnings: list[str] = []
    out = tmp_path / "planned.pptx"
    result = render_deck(plan, pack, library, out, warnings=warnings)
    assert result.out_path == out
    assert result.slide_count == len(plan.slides)
    assert out.is_file() and out.stat().st_size > 0
    assert not [w for w in warnings if "no blueprint for archetype" in w], warnings

    deck = extract_deck(out)
    assert deck.slide_count == len(plan.slides)
    assert deck.aspect_ratio == pack.aspect_ratios[0] == "16:9"
    assert all(slide.aspect_ratio == "16:9" for slide in deck.slides)
    for slide in deck.slides:
        assert _slide_texts(slide), f"slide {slide.index} rendered no text"


# --------------------------------------------------------------------------- #
# Golden plan: fixed content, native data, speaker notes
# --------------------------------------------------------------------------- #
def test_golden_plan_renders_text_notes_and_native_data(learned, tmp_path: Path) -> None:
    pack: FormatPack = learned["pack"]
    library: BlueprintLibrary = learned["library"]
    plan = _golden_plan(pack)
    assert {s.archetype for s in plan.slides} <= set(library.archetypes())

    warnings: list[str] = []
    out = tmp_path / "golden.pptx"
    result = render_deck(plan, pack, library, out, warnings=warnings)
    assert result.slide_count == 5
    # every slot in the golden plan exists in the learned blueprints
    assert warnings == [], warnings

    deck = extract_deck(out)
    assert deck.slide_count == len(plan.slides)
    assert deck.aspect_ratio == pack.aspect_ratios[0]
    for slide in deck.slides:
        assert _slide_texts(slide), f"slide {slide.index} rendered no text"

    title, number, chart_slide, table_slide, quote = deck.slides

    assert "DeckForge end to end" in _slide_texts(title)
    assert "Q3 2026" in _slide_texts(title)
    assert "12" in _slide_texts(number)
    assert "decks analysed into the pack" in _slide_texts(number)

    assert len(chart_slide.charts) == 1
    chart = chart_slide.charts[0]
    assert chart.categories == ["Q1", "Q2", "Q3", "Q4"]
    assert [s.name for s in chart.series] == ["Plan"]
    assert list(chart.series[0].values) == [1.0, 1.2, 1.4, 1.6]
    assert "Revenue by quarter" in _slide_texts(chart_slide)

    assert len(table_slide.tables) == 1
    table = table_slide.tables[0]
    assert table.col_count == 3
    # the header row is written into row 0 of the table itself; the renderer
    # deliberately clears the OOXML first-row flag (tables.add_table sets
    # ``table.first_row = False``) because the pack paints the header.
    assert table.rows == [
        ["Metric", "Actual", "Plan"],
        ["Revenue", "$4.2M", "$3.9M"],
        ["NPS", "91", "85"],
    ]
    assert table.header_row_count == 0

    assert "A plan without an owner is a wish list." in _slide_texts(quote)

    # speaker notes survive the round trip; the slide planned without notes has none
    assert [bool(slide.notes_text) for slide in deck.slides] == [
        True,
        True,
        True,
        False,
        True,
    ]
    assert number.notes_text == plan.slides[1].speaker_notes


# --------------------------------------------------------------------------- #
# QA: deterministic checks only, no renderer
# --------------------------------------------------------------------------- #
def test_qa_deterministic_pass_runs_without_a_renderer(learned, tmp_path: Path) -> None:
    pack: FormatPack = learned["pack"]
    library: BlueprintLibrary = learned["library"]
    plan = _golden_plan(pack)

    report = run_qa(
        plan, pack, library, render_backend="none", out_dir=tmp_path / "qa"
    )
    assert report.rendered is False
    assert report.deck_path is None
    assert report.pack == pack.name
    assert [slide.slide_n for slide in report.slides] == [1, 2, 3, 4, 5]
    assert all(isinstance(slide.issues, list) for slide in report.slides)

    tainted = plan.model_copy(deep=True)
    tainted.slides[1].slots["caption"] = SlotValue(text="the new tier is coming soon")
    flagged = run_qa(
        tainted, pack, library, render_backend="none", out_dir=tmp_path / "qa2"
    )
    banned = [
        issue
        for slide in flagged.slides
        for issue in slide.issues
        if issue.check == QACheckType.BANNED_PHRASE
    ]
    assert [issue.slide_n for issue in banned] == [2], banned


# --------------------------------------------------------------------------- #
# Reproducibility: same seed + same plan => same bytes
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pipeline_is_byte_identical_across_runs(learned, tmp_path: Path) -> None:
    pack: FormatPack = learned["pack"]
    library: BlueprintLibrary = learned["library"]
    plan = _golden_plan(pack)

    first = tmp_path / "run_a"
    second = tmp_path / "run_b"
    for root in (first, second):
        assert gc.main(
            ["--out", str(root / "corpus"), "--decks", str(CORPUS_DECKS),
             "--seed", str(CORPUS_SEED)]
        ) == 0
        learn_pack(
            root / "corpus", "e2e", target_dir=root / "pack", use_cache=False
        )
        render_deck(plan, pack, library, root / "deck.pptx")

    decks_a = sorted((first / "corpus").glob("*.pptx"))
    decks_b = sorted((second / "corpus").glob("*.pptx"))
    assert len(decks_a) == len(decks_b) == CORPUS_DECKS
    for path_a, path_b in zip(decks_a, decks_b):
        assert path_a.name == path_b.name
        assert _sha256(path_a) == _sha256(path_b), f"{path_a.name} is not reproducible"

    for relative in ("style_profile.json", "manifest.json"):
        assert (first / "pack" / relative).read_bytes() == (
            second / "pack" / relative
        ).read_bytes(), relative
    blueprints_a = sorted((first / "pack" / "blueprints").glob("*.json"))
    assert blueprints_a
    for path_a in blueprints_a:
        path_b = second / "pack" / "blueprints" / path_a.name
        assert path_a.read_bytes() == path_b.read_bytes(), path_a.name

    # pack.json carries a wall-clock created_at; everything else must match
    pack_a, _ = load_pack(first / "pack")
    pack_b, _ = load_pack(second / "pack")
    assert pack_a.model_dump(mode="json", exclude={"created_at"}) == pack_b.model_dump(
        mode="json", exclude={"created_at"}
    )

    assert _sha256(first / "deck.pptx") == _sha256(second / "deck.pptx")


# --------------------------------------------------------------------------- #
# Corpus fetcher: CLI contract only, never the network
# --------------------------------------------------------------------------- #
def _run_fetch(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FETCH_CORPUS), *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=REPO_ROOT,
    )


def test_fetch_corpus_cli_is_offline_and_self_describing() -> None:
    assert FETCH_CORPUS.is_file()

    helped = _run_fetch("--help")
    assert helped.returncode == 0
    assert "fetch_corpus.py" in helped.stdout

    listed = _run_fetch("--list")
    assert listed.returncode == 0
    assert "Apache-2.0" in listed.stdout
    assert "raw.githubusercontent.com" in listed.stdout
    assert len([line for line in listed.stdout.splitlines() if "http" in line]) == 8

    unknown = _run_fetch("--only", "no-such-deck", "--out", "unused")
    assert unknown.returncode == 2
    assert "unknown deck" in unknown.stderr
