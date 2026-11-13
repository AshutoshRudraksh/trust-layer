"""Hardening ticket 6: the chart is generated from runs/pyx_h9_20261102b/RESULTS.md (ADR 0005, item 4).

RESULTS.md is read, never written. The committed SVG must equal what the generator produces from it,
so the chart cannot drift from the record.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pyx.results_chart import parse_headline, render_svg

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "runs" / "pyx_h9_20261102b" / "RESULTS.md"
CHART = ROOT / "docs" / "charts" / "pyx_h9_20261102b_pass_rate.svg"
RESULTS_SHA256 = "bb1f891cc9f72b759ccbf5f7350435f46458dce97034cad70ef9caefc4b796f7"


def test_results_md_is_the_frozen_file() -> None:
    assert hashlib.sha256(RESULTS.read_bytes()).hexdigest() == RESULTS_SHA256


def test_headline_rows_are_the_settled_numbers() -> None:
    rows = parse_headline(RESULTS.read_text(encoding="utf-8"))
    assert [(r.arm, r.rate) for r in rows] == [
        ("earned_lessons (1 lesson)", "0.625"),
        ("free_lessons (11 lessons)", "0.5208"),
        ("no_memory", "0.4375"),
        ("raw_traces", "0.4375"),
    ]


def test_parse_refuses_a_file_without_the_headline_table() -> None:
    with pytest.raises(ValueError, match="headline"):
        parse_headline("# Results\n\nno table here\n")


def test_svg_shows_every_rate_and_the_caveat() -> None:
    svg = render_svg(parse_headline(RESULTS.read_text(encoding="utf-8")))
    for label in ("0.625", "0.5208", "0.4375", "earned_lessons", "raw_traces"):
        assert label in svg
    assert "No answer in any arm passed the full rubric" in svg
    assert "6 paired task and repetition cells" in svg


def test_committed_chart_equals_the_generated_chart() -> None:
    assert CHART.read_text(encoding="utf-8") == render_svg(parse_headline(RESULTS.read_text(encoding="utf-8")))
