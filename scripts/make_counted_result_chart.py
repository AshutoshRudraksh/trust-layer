"""Draw the counted result as a bar chart, straight from the committed run record.

  python3 scripts/make_counted_result_chart.py [RESULTS.md] [OUT.svg]

Defaults: runs/pyx_h9_20261102b/RESULTS.md in, docs/counted_result_chart.svg out.
The script reads the first table under "## Headline" whose second column is the
headline metric, and draws one bar per arm with the value exactly as the table
prints it. The SVG uses no dependencies, no fonts beyond a generic family, no
timestamps and no random ids, so the same RESULTS.md always gives the same bytes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "runs" / "pyx_h9_20261102b" / "RESULTS.md"
OUT = ROOT / "docs" / "counted_result_chart.svg"
RUN_ID = "pyx_h9_20261102b"

WIDTH = 720
BAR_W = 110
GAP = 40
LEFT = 70
TOP = 70
PLOT_H = 300
TICKS = ("0", "0.25", "0.5", "0.75", "1")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_headline(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (metric name, [(arm, value as printed)]) from the Headline table."""
    lines = text.splitlines()
    try:
        start = lines.index("## Headline")
    except ValueError:
        raise ValueError("RESULTS.md has no '## Headline' section") from None
    i = start + 1
    while i < len(lines) and not lines[i].startswith("|"):
        if lines[i].startswith("## "):
            raise ValueError("Headline section has no table")
        i += 1
    if i >= len(lines):
        raise ValueError("Headline section has no table")
    header = _cells(lines[i])
    if len(header) < 2 or header[0] != "Arm":
        raise ValueError(f"unexpected headline table header: {header}")
    metric = header[1]
    rows: list[tuple[str, str]] = []
    for line in lines[i + 2:]:
        if not line.startswith("|"):
            break
        cells = _cells(line)
        float(cells[1])  # the value must be a number
        rows.append((cells[0], cells[1]))
    if not rows:
        raise ValueError("headline table has no rows")
    return metric, rows


def bar_height(value: str) -> str:
    """Bar height in pixels on a 0 to 1 axis, rounded to 2 places so the bytes are stable."""
    return f"{float(value) * PLOT_H:.2f}"


def render_svg(text: str) -> str:
    metric, rows = parse_headline(text)
    n = len(rows)
    plot_w = n * BAR_W + (n + 1) * GAP
    width = max(WIDTH, LEFT + plot_w + 30)
    height = TOP + PLOT_H + 90
    base = TOP + PLOT_H
    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" role="img" '
        f'aria-label="{escape(metric)} by arm, run {RUN_ID}">'
    )
    out.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')
    out.append(
        f'<text x="{LEFT}" y="30" font-size="18" font-weight="bold" fill="#111111">'
        f"{escape(metric)} by arm</text>"
    )
    out.append(
        f'<text x="{LEFT}" y="50" font-size="12" fill="#555555">'
        f"run {RUN_ID}, values from runs/{RUN_ID}/RESULTS.md</text>"
    )
    for t in TICKS:
        y = f"{base - float(t) * PLOT_H:.2f}"
        out.append(
            f'<line x1="{LEFT}" y1="{y}" x2="{LEFT + plot_w}" y2="{y}" stroke="#dddddd" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{LEFT - 8}" y="{y}" font-size="11" fill="#555555" text-anchor="end" '
            f'dominant-baseline="middle">{t}</text>'
        )
    out.append(
        f'<line x1="{LEFT}" y1="{base}" x2="{LEFT + plot_w}" y2="{base}" stroke="#333333" stroke-width="1"/>'
    )
    for k, (arm, value) in enumerate(rows):
        x = LEFT + GAP + k * (BAR_W + GAP)
        h = bar_height(value)
        y = f"{base - float(h):.2f}"
        fill = "#2f6fdf" if k == 0 else "#9aa5b1"
        cx = x + BAR_W // 2
        out.append(
            f'<rect class="bar" data-arm="{escape(arm)}" data-value="{escape(value)}" '
            f'x="{x}" y="{y}" width="{BAR_W}" height="{h}" fill="{fill}"/>'
        )
        out.append(
            f'<text x="{cx}" y="{float(y) - 6:.2f}" font-size="13" font-weight="bold" '
            f'fill="#111111" text-anchor="middle">{escape(value)}</text>'
        )
        name, _, note = arm.partition(" (")
        out.append(
            f'<text x="{cx}" y="{base + 20}" font-size="12" fill="#111111" text-anchor="middle">'
            f"{escape(name)}</text>"
        )
        if note:
            out.append(
                f'<text x="{cx}" y="{base + 36}" font-size="11" fill="#555555" text-anchor="middle">'
                f"({escape(note)}</text>"
            )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else RESULTS
    dst = Path(argv[2]) if len(argv) > 2 else OUT
    svg = render_svg(src.read_text(encoding="utf-8"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(svg.encode("utf-8"))
    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
