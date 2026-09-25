"""Archetype detection (Workstream B): hand-built slides must map to the
declared archetype with a confident score."""

from __future__ import annotations

from deckforge_core.analysis.archetype import detect_archetype
from deckforge_core.schemas.extracted import (
    ExtractedChart,
    ExtractedChartSeries,
    ExtractedImageRef,
    ExtractedParagraph,
    ExtractedShape,
    ExtractedSlide,
    ExtractedTable,
    ExtractedTextRun,
)


def _run(text: str, size: float = 14.0, *, bold: bool = False) -> ExtractedTextRun:
    return ExtractedTextRun(text=text, size_pt=size, bold=bold)


def _para(text: str, size: float = 14.0, *, bold: bool = False) -> ExtractedParagraph:
    return ExtractedParagraph(runs=[_run(text, size, bold=bold)])


def _shape(
    x: float,
    y: float,
    w: float,
    h: float,
    paras: list[ExtractedParagraph],
    *,
    shape_type: str = "TEXT_BOX",
    image: ExtractedImageRef | None = None,
) -> ExtractedShape:
    return ExtractedShape(
        shape_type=shape_type, x=x, y=y, w=w, h=h, text=paras, image=image
    )


def _img() -> ExtractedImageRef:
    return ExtractedImageRef(embedded_part_name="img.png", width_px=64, height_px=64)


def _slide(
    index: int,
    shapes: list[ExtractedShape] | None = None,
    *,
    charts: list[ExtractedChart] | None = None,
    tables: list[ExtractedTable] | None = None,
) -> ExtractedSlide:
    return ExtractedSlide(
        index=index,
        shapes=shapes or [],
        charts=charts or [],
        tables=tables or [],
    )


def test_title_detected():
    slide = _slide(
        1,
        [
            _shape(0.04, 0.07, 0.9, 0.07, [_para("Q3 2026", 13, bold=True)]),
            _shape(0.04, 0.2, 0.92, 0.13, [_para("Building the category", 30, bold=True)]),
            _shape(0.04, 0.36, 0.65, 0.1, [_para("A working document for the team", 16)]),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "title"
    assert conf >= 0.8


def test_section_divider_detected():
    slide = _slide(
        2,
        [
            _shape(0.04, 0.07, 0.9, 0.07, [_para("AGENDA", 13, bold=True)]),
            _shape(0.04, 0.4, 0.9, 0.12, [_para("The user problem", 26, bold=True)]),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "section-divider"
    assert conf >= 0.7


def test_big_number_detected():
    slide = _slide(
        3,
        [
            _shape(0.06, 0.28, 0.88, 0.3, [_para("91", 72, bold=True)]),
            _shape(0.06, 0.62, 0.88, 0.08, [_para("Users up year over year", 16)]),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "big-number"
    assert conf >= 0.8


def test_hero_word_is_not_big_number():
    slide = _slide(
        4,
        [
            _shape(0.06, 0.3, 0.88, 0.2, [_para("Vision", 60, bold=True)]),
            _shape(0.06, 0.62, 0.88, 0.08, [_para("Where we are headed", 14)]),
        ],
    )
    archetype, _ = detect_archetype(slide)
    assert archetype != "big-number"


def test_quote_detected():
    slide = _slide(
        5,
        [
            _shape(
                0.08, 0.3, 0.84, 0.3,
                [_para("\u201cCustomer success is the only strategy that works.\u201d", 24)],
            ),
            _shape(0.08, 0.62, 0.4, 0.08, [_para("Founder, 2025", 12)]),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "quote"
    assert conf >= 0.8


def test_chart_detected():
    chart = ExtractedChart(
        chart_type="COLUMN_CLUSTERED",
        categories=["Q1", "Q2"],
        series=[ExtractedChartSeries(name="Revenue", values=[1.0, 2.0])],
    )
    slide = _slide(
        6,
        [_shape(0.04, 0.07, 0.9, 0.06, [_para("Trend", 13, bold=True)])],
        charts=[chart],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "chart"
    assert conf >= 0.8


def test_table_detected():
    table = ExtractedTable(
        rows=[["Metric", "Value"], ["ARR", "1.2m"]],
        header_row_count=1,
        col_count=2,
    )
    slide = _slide(7, charts=[], tables=[table])
    archetype, conf = detect_archetype(slide)
    assert archetype == "table"
    assert conf >= 0.8


def test_full_bleed_image_detected():
    slide = _slide(
        8,
        [
            _shape(
                0, 0, 1.0, 1.0,
                [],
                shape_type="PICTURE",
                image=_img(),
            )
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "full-bleed-image"
    assert conf >= 0.8


def test_image_left_detected():
    slide = _slide(
        9,
        [
            _shape(
                0.03, 0.15, 0.47, 0.6,
                [],
                shape_type="PICTURE",
                image=_img(),
            ),
            _shape(
                0.58, 0.15, 0.38, 0.08,
                [_para("Customers love it", 30, bold=True)],
            ),
            _shape(
                0.58, 0.28, 0.38, 0.4,
                [
                    _para("Teams that ship weekly see retention rise steadily.", 16),
                    _para("The feedback loop keeps shortening every quarter.", 16),
                ],
            ),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "image-left"
    assert conf >= 0.7


def test_two_column_text_detected():
    slide = _slide(
        10,
        [
            _shape(
                0.05, 0.2, 0.43, 0.5,
                [
                    _para("The first column explains the full historical context of the release.", 14),
                    _para("It continues with more detail about that period.", 14),
                ],
            ),
            _shape(
                0.52, 0.2, 0.43, 0.5,
                [
                    _para("The second column covers the financial outcomes reported today.", 14),
                    _para("These numbers support the final recommendation here.", 14),
                ],
            ),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "two-column-text"
    assert conf >= 0.6


def test_three_cards_detected():
    slide = _slide(
        11,
        [
            _shape(0.05, 0.06, 0.9, 0.09, [_para("Where we win", 20, bold=True)]),
            _shape(0.05, 0.45, 0.28, 0.35, [_para("Bookings grew every week this quarter.", 14)]),
            _shape(0.36, 0.45, 0.28, 0.35, [_para("Support offered instant answers to clients.", 14)]),
            _shape(0.67, 0.45, 0.28, 0.35, [_para("Retention stayed at ninety five percent.", 14)]),
        ],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "three-cards"
    assert conf >= 0.6


def test_unrecognised_falls_back_to_two_column():
    slide = _slide(
        12,
        [_shape(0.05, 0.2, 0.3, 0.1, [_para("tiny note", 12)])],
    )
    archetype, conf = detect_archetype(slide)
    assert archetype == "two-column-text"
    assert conf == 0.2
