"""Chart of the counted run's headline, generated from runs/pyx_h9_20261102b/RESULTS.md (ticket 6).

RESULTS.md is only read. The SVG is plain text with no dependency, so a test can regenerate it and
compare it byte for byte with the committed file.

    python -m pyx.results_chart runs/pyx_h9_20261102b/RESULTS.md docs/charts/pyx_h9_20261102b_pass_rate.svg
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import List

HEADER = "| Arm | Criterion pass rate | T1 | T2 |"
CAVEAT = ("No answer in any arm passed the full rubric. Criterion pass rate, cycle 1, "
          "over 6 paired task and repetition cells.")


@dataclass(frozen=True)
class Row:
    arm: str
    rate: str  # kept as printed in RESULTS.md, so the chart shows the record's own digits
    t1: str
    t2: str


def parse_headline(text: str) -> List[Row]:
    lines = text.splitlines()
    if HEADER not in lines:
        raise ValueError("RESULTS.md has no headline table")
    rows = []
    for line in lines[lines.index(HEADER) + 2:]:
        if not line.startswith("|"):
            break
        arm, rate, t1, t2 = [c.strip() for c in line.strip("|").split("|")]
        rows.append(Row(arm, rate, t1, t2))
    return rows


def render_svg(rows: List[Row]) -> str:
    left, width, bar_h, gap, top = 230, 400, 26, 12, 50
    height = top + len(rows) * (bar_h + gap) + 50
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" font-family="sans-serif" font-size="13">',
        '<text x="10" y="24" font-size="15" font-weight="bold">Pyx counted run pyx_h9_20261102b: criterion pass rate by arm</text>',
    ]
    for i, r in enumerate(rows):
        y = top + i * (bar_h + gap)
        w = round(float(r.rate) * width, 1)
        out.append(f'<text x="10" y="{y + 18}">{escape(r.arm)}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{w}" height="{bar_h}" fill="#4a6fa5"/>')
        out.append(f'<text x="{left + w + 6}" y="{y + 18}">{r.rate}</text>')
    out.append(f'<text x="10" y="{height - 30}" font-size="12">{escape(CAVEAT)}</text>')
    out.append(f'<text x="10" y="{height - 12}" font-size="12">Generated from runs/pyx_h9_20261102b/RESULTS.md by pyx/results_chart.py.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: List[str]) -> None:
    src, dst = Path(argv[0]), Path(argv[1])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(render_svg(parse_headline(src.read_text(encoding="utf-8"))), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
