"""End-to-end renderer tests (Workstream C) — python-pptx only, no COM."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from deckforge_core.renderer import render_deck
from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import (
    AlternateArrangement,
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
)
from deckforge_core.schemas.deck_plan import (
    ChartSeries,
    ChartSpec,
    DeckPlan,
    ImageReq,
    SlidePlan,
    SlotValue,
    TableSpec,
)
from deckforge_core.schemas.pack import FormatPack


# --------------------------------------------------------------------------- #
# Blueprint + plan fixtures
# --------------------------------------------------------------------------- #
def _slot(
    name,
    x,
    y,
    w,
    h,
    style="body",
    kinds=None,
    align="left",
    valign="top",
    optional=False,
    image_fit="crop",
):
    return SlotDef(
        name=name,
        kinds=kinds or [ContentKind.TEXT],
        region=SlotRegion(x=x, y=y, w=w, h=h),
        style=style,
        align=align,
        valign=valign,
        optional=optional,
        image_fit=image_fit,
    )


def _library() -> BlueprintLibrary:
    return BlueprintLibrary(
        [
            Blueprint(
                id="title",
                archetype=Archetype.TITLE,
                slots=[
                    _slot("kicker", 0.1, 0.12, 0.8, 0.08, "kicker", align="center"),
                    _slot("title", 0.1, 0.22, 0.8, 0.25, "h1", align="center"),
                    _slot("subtitle", 0.1, 0.5, 0.8, 0.12, "body", align="center"),
                    _slot("author", 0.1, 0.64, 0.8, 0.1, "caption", align="center"),
                ],
            ),
            Blueprint(
                id="big-number",
                archetype=Archetype.BIG_NUMBER,
                slots=[
                    _slot(
                        "number", 0.1, 0.22, 0.8, 0.4, "big-number",
                        align="center", valign="middle",
                    ),
                    _slot("caption", 0.1, 0.64, 0.8, 0.12, "body", align="center"),
                    _slot("source", 0.1, 0.78, 0.8, 0.08, "caption", align="center"),
                ],
                default_order=["number", "caption", "source"],
            ),
            Blueprint(
                id="three-cards",
                archetype=Archetype.THREE_CARDS,
                slots=[
                    _slot("title", 0.08, 0.06, 0.84, 0.12, "h2"),
                    _slot("card_1", 0.06, 0.22, 0.27, 0.6, "body", optional=True),
                    _slot("card_2", 0.365, 0.22, 0.27, 0.6, "body", optional=True),
                    _slot("card_3", 0.67, 0.22, 0.27, 0.6, "body", optional=True),
                ],
            ),
            Blueprint(
                id="chart",
                archetype=Archetype.CHART,
                slots=[
                    _slot("title", 0.08, 0.05, 0.84, 0.1, "h2"),
                    _slot("chart", 0.08, 0.18, 0.84, 0.62, kinds=[ContentKind.CHART]),
                    _slot("source", 0.08, 0.84, 0.84, 0.08, "caption"),
                ],
            ),
            Blueprint(
                id="table",
                archetype=Archetype.TABLE,
                slots=[
                    _slot("title", 0.08, 0.05, 0.84, 0.1, "h2"),
                    _slot("table", 0.08, 0.18, 0.84, 0.62, kinds=[ContentKind.TABLE]),
                    _slot("source", 0.08, 0.84, 0.84, 0.08, "caption"),
                ],
            ),
            Blueprint(
                id="image-right",
                archetype=Archetype.IMAGE_RIGHT,
                slots=[
                    _slot("title", 0.55, 0.08, 0.4, 0.12, "h2"),
                    _slot("body", 0.55, 0.22, 0.4, 0.6, "body"),
                    _slot(
                        "image", 0.06, 0.08, 0.44, 0.8,
                        kinds=[ContentKind.IMAGE], image_fit="crop",
                    ),
                    _slot("source", 0.06, 0.9, 0.44, 0.06, "caption"),
                ],
            ),
            Blueprint(
                id="two-column-text",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("kicker", 0.08, 0.05, 0.84, 0.08, "kicker"),
                    _slot("col_a_heading", 0.08, 0.16, 0.42, 0.1, "h2"),
                    _slot("col_a_body", 0.08, 0.28, 0.42, 0.6, "body"),
                    _slot("col_b_heading", 0.52, 0.16, 0.42, 0.1, "h2"),
                    _slot("col_b_body", 0.52, 0.28, 0.42, 0.6, "body"),
                ],
            ),
        ]
    )


def _plan(img_path: Path) -> DeckPlan:
    return DeckPlan(
        title="Renderer E2E",
        aspect_ratio="16:9",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="title",
                slots={
                    "kicker": SlotValue(text="Quarterly Review"),
                    "title": SlotValue(text="DeckForge Q3 Update"),
                    "subtitle": SlotValue(text="Rendering real decks since 2026"),
                    "author": SlotValue(text="Pranav · DeckForge"),
                },
            ),
            SlidePlan(
                n=2,
                archetype="big-number",
                title="Churn fell 12%",
                slots={
                    "number": SlotValue(number="12%"),
                    "caption": SlotValue(text="monthly churn after the onboarding rework"),
                    "source": SlotValue(text="Source: internal analytics"),
                },
                speaker_notes="Walk through the onboarding revamp.",
            ),
            SlidePlan(
                n=3,
                archetype="big-number",
                slots={
                    "number": SlotValue(number=42),
                    "caption": SlotValue(text="cards designed this sprint"),
                },
            ),
            SlidePlan(
                n=4,
                archetype="three-cards",
                title="Three focus areas",
                slots={
                    "title": SlotValue(text="Three focus areas"),
                    "card_1": SlotValue(
                        text="Render",
                        paragraphs=["Native pptx with real fonts and colours"],
                    ),
                    "card_2": SlotValue(
                        text="QA", paragraphs=["Render and diff against the reference deck"]
                    ),
                    "card_3": SlotValue(
                        text="Ship", paragraphs=["A pack in your hands, not a mock"]
                    ),
                },
            ),
            SlidePlan(
                n=5,
                archetype="chart",
                title="Revenue by quarter",
                slots={
                    "title": SlotValue(text="Revenue by quarter"),
                    "chart": SlotValue(
                        chart=ChartSpec(
                            chart_type="column",
                            categories=["Q1", "Q2", "Q3", "Q4"],
                            series=[ChartSeries(name="2026", values=[100.0, 120.0, 140.0, 180.0])],
                            show_legend=False,
                        )
                    ),
                    "source": SlotValue(text="Source: finance"),
                },
            ),
            SlidePlan(
                n=6,
                archetype="table",
                title="Quarterly metrics",
                slots={
                    "title": SlotValue(text="Quarterly metrics"),
                    "table": SlotValue(
                        table=TableSpec(
                            columns=["Metric", "Q1", "Q2"],
                            rows=[["MRR", "100k", "140k"], ["Churn", "12%", "9%"]],
                        )
                    ),
                },
            ),
            SlidePlan(
                n=7,
                archetype="image-right",
                title="Where we are",
                slots={
                    "title": SlotValue(text="Where we are"),
                    "body": SlotValue(
                        paragraphs=[
                            "We ship native pptx files with the pack look.",
                            "No screenshots, no LibreOffice.",
                        ]
                    ),
                    "image": SlotValue(
                        image=ImageReq(url=str(img_path), alt="deck render")
                    ),
                    "source": SlotValue(text="DeckForge"),
                },
            ),
            SlidePlan(
                n=8,
                archetype="two-column-text",
                title="Two columns",
                slots={
                    "kicker": SlotValue(text="Comparison"),
                    "col_a_heading": SlotValue(text="Before"),
                    "col_a_body": SlotValue(
                        paragraphs=["Hand-made decks", "Random fonts and colours"]
                    ),
                    "col_b_heading": SlotValue(text="After"),
                    "col_b_body": SlotValue(
                        paragraphs=["Packs from real decks", "Only the pack's fonts and palette"]
                    ),
                },
            ),
        ],
    )


def _shape_text(shape) -> str:
    if not shape.has_text_frame:
        return ""
    return "\n".join(
        run.text
        for paragraph in shape.text_frame.paragraphs
        for run in paragraph.runs
    )


def _slide_texts(slide) -> list[str]:
    return [_shape_text(shape) for shape in slide.shapes]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    path = tmp_path / "photo.png"
    Image.new("RGB", (400, 300), (120, 90, 60)).save(path)
    return path


def test_render_full_deck(canonical_pack: FormatPack, sample_image: Path, tmp_path: Path):
    out_path = tmp_path / "deck.pptx"
    warnings: list[str] = []
    result = render_deck(
        _plan(sample_image), canonical_pack, _library(), out_path, warnings=warnings
    )

    assert result.out_path == out_path
    assert result.slide_count == 8
    assert result.warnings == warnings

    prs = Presentation(str(out_path))
    assert len(prs.slides) == 8
    assert int(prs.slide_width) == 12192000
    assert int(prs.slide_height) == 6858000

    # title slide text
    slide1_texts = _slide_texts(prs.slides[0])
    assert any("DeckForge Q3 Update" in t for t in slide1_texts)
    assert any("QUARTERLY REVIEW" in t for t in slide1_texts)
    # big-number accents the number, still same string
    assert any("12%" in t for t in _slide_texts(prs.slides[1]))
    # every slide has content shapes
    for slide in prs.slides:
        assert len(list(slide.shapes)) > 0

    # chart slide has a native chart
    chart_slide = prs.slides[4]
    assert any(shape.has_chart for shape in chart_slide.shapes)

    # table slide has a native table
    table_slide = prs.slides[5]
    table_graphic = next(s for s in table_slide.shapes if s.has_table)
    table = table_graphic.table
    assert table.cell(0, 0).text == "Metric"
    assert table.cell(1, 0).text == "MRR"
    assert table.cell(1, 1).text == "100k"

    # notes survived
    assert prs.slides[1].notes_slide.notes_text_frame.text == (
        "Walk through the onboarding revamp."
    )

    # the local image became a picture shape (framed), not a placeholder
    image_slide = prs.slides[6]
    pictures = [
        s for s in image_slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE
    ]
    assert pictures, "expected a real picture on the image slide"
    assert not any("image placeholder" in t for t in _slide_texts(image_slide))

    # three-cards carries card heading + body text
    cards_text = _slide_texts(prs.slides[3])
    assert any("Render" in t for t in cards_text)
    assert any("Native pptx" in t for t in cards_text)


def test_unknown_slot_key_warns(
    canonical_pack: FormatPack, tmp_path: Path
):
    plan = DeckPlan(
        title="x", aspect_ratio="16:9", pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="title",
                slots={
                    "title": SlotValue(text="Hello"),
                    "totally_bogus": SlotValue(text="nope"),
                },
            )
        ],
    )
    warnings: list[str] = []
    render_deck(plan, canonical_pack, _library(), tmp_path / "o.pptx", warnings=warnings)
    assert any("unused slot 'totally_bogus'" in w for w in warnings)


def test_empty_required_slot_warns_and_outlines(
    canonical_pack: FormatPack, tmp_path: Path
):
    plan = DeckPlan(
        title="x", aspect_ratio="16:9", pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="big-number",
                title="Number only",
                slots={"number": SlotValue(number=7)},
            )
        ],
    )
    warnings: list[str] = []
    out = tmp_path / "o.pptx"
    render_deck(plan, canonical_pack, _library(), out, warnings=warnings)
    assert any("empty required slot caption" in w for w in warnings)

    prs = Presentation(str(out))
    assert any("[empty: caption]" in t for t in _slide_texts(prs.slides[0]))


def test_missing_blueprint_falls_back_with_warning(
    canonical_pack: FormatPack, tmp_path: Path
):
    plan = DeckPlan(
        title="x", aspect_ratio="16:9", pack="demo",
        slides=[SlidePlan(n=1, archetype="no-such-archetype", title="fallback title")],
    )
    warnings: list[str] = []
    render_deck(plan, canonical_pack, _library(), tmp_path / "o.pptx", warnings=warnings)
    assert any("no blueprint for archetype" in w for w in warnings)


def test_long_body_text_auto_shrinks(
    canonical_pack: FormatPack, tmp_path: Path
):
    huge = "".join(["agglomeration jargon conversation "] * 250)
    plan = DeckPlan(
        title="x", aspect_ratio="16:9", pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="two-column-text",
                slots={
                    "col_a_heading": SlotValue(text="Long copy"),
                    "col_a_body": SlotValue(paragraphs=[huge]),
                    "col_b_heading": SlotValue(text="Right"),
                    "col_b_body": SlotValue(paragraphs=["short"]),
                },
            )
        ],
    )
    warnings: list[str] = []
    out = tmp_path / "o.pptx"
    render_deck(plan, canonical_pack, _library(), out, warnings=warnings)
    assert any("shrunk" in w and "col_a_body" in w for w in warnings), warnings

    prs = Presentation(str(out))
    small_runs = []
    for shape in prs.slides[0].shapes:
        if not shape.has_text_frame:
            continue
        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                if run.text and "agglomeration" in run.text:
                    small_runs.append(run.font.size.pt if run.font.size else None)
    assert small_runs, "expected the long body text to be present"
    assert all(size < 16.0 for size in small_runs if size is not None)


def _library_with_portrait_alternate() -> BlueprintLibrary:
    blueprint = Blueprint(
        id="big-number",
        archetype=Archetype.BIG_NUMBER,
        slots=[
            _slot("number", 0.1, 0.25, 0.8, 0.4, "big-number", align="center", valign="middle"),
            _slot("caption", 0.1, 0.66, 0.8, 0.15, "body", align="center"),
        ],
        default_order=["number", "caption"],
    )
    blueprint.alternatives.append(
        AlternateArrangement(
            aspect_ratio="portrait",
            description="stack number above caption on tall pages",
            slots=[
                _slot("number", 0.1, 0.15, 0.8, 0.3, "big-number", align="center", valign="middle"),
                _slot("caption", 0.1, 0.5, 0.8, 0.2, "body", align="center"),
            ],
        )
    )
    return BlueprintLibrary([blueprint])


def _number_relative_top(deck_file: Path, text: str) -> float:
    prs = Presentation(str(deck_file))
    slide = prs.slides[0]
    height = int(prs.slide_height)
    for shape in slide.shapes:
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                if any(run.text.strip() == text for run in paragraph.runs):
                    return shape.top / height
    raise AssertionError(f"text {text!r} not found on slide")


def test_aspect_ratio_alternates_rerender(canonical_pack: FormatPack, tmp_path: Path):
    lib = _library_with_portrait_alternate()
    slots = {"number": SlotValue(number="99"), "caption": SlotValue(text="caption here")}

    landscape = tmp_path / "16x9.pptx"
    render_deck(
        DeckPlan(title="x", pack="demo", aspect_ratio="16:9", slides=[SlidePlan(n=1, archetype="big-number", slots=slots)]),
        canonical_pack, lib, landscape,
    )
    standard = tmp_path / "4x3.pptx"
    render_deck(
        DeckPlan(title="x", pack="demo", aspect_ratio="4:3", slides=[SlidePlan(n=1, archetype="big-number", slots=slots)]),
        canonical_pack, lib, standard,
    )
    portrait = tmp_path / "portrait.pptx"
    render_deck(
        DeckPlan(title="x", pack="demo", aspect_ratio="portrait", slides=[SlidePlan(n=1, archetype="big-number", slots=slots)]),
        canonical_pack, lib, portrait,
    )

    landscape_top = _number_relative_top(landscape, "99")
    standard_top = _number_relative_top(standard, "99")
    portrait_top = _number_relative_top(portrait, "99")

    assert landscape_top == pytest.approx(0.25)
    assert standard_top == pytest.approx(0.25)
    assert portrait_top == pytest.approx(0.15)
    # the alternate must actually move the slot, and portrait must not squash
    assert portrait_top != landscape_top

    prs = Presentation(str(portrait))
    assert int(prs.slide_height) > int(prs.slide_width)  # genuinely portrait
    assert portrait_top > 0.0 < 1.0
    assert 0.0 <= portrait_top + 0.3 <= 1.0


def test_render_is_deterministic_and_idempotent(
    canonical_pack: FormatPack, sample_image: Path, tmp_path: Path
):
    first = tmp_path / "a.pptx"
    second = tmp_path / "b.pptx"
    render_deck(_plan(sample_image), canonical_pack, _library(), first)
    render_deck(_plan(sample_image), canonical_pack, _library(), second)

    import hashlib

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(
        second.read_bytes()
    ).digest()
