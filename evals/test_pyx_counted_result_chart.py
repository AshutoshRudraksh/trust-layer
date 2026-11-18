"""Step 3 test: the committed counted result chart is exactly what RESULTS.md draws.

The SVG is regenerated in memory from runs/pyx_h9_20261102b/RESULTS.md and must
match docs/counted_result_chart.svg byte for byte, and every bar must carry the
value its row prints in the headline table.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "runs" / "pyx_h9_20261102b" / "RESULTS.md"
SVG = ROOT / "docs" / "counted_result_chart.svg"
sys.path.insert(0, str(ROOT / "scripts"))

from make_counted_result_chart import PLOT_H, render_svg  # noqa: E402

BAR = re.compile(r'<rect class="bar" data-arm="([^"]*)" data-value="([^"]*)" [^>]*height="([^"]*)"')


def _table_rows() -> list[tuple[str, str]]:
    """Read the headline table directly, without the script's parser."""
    text = RESULTS.read_text(encoding="utf-8")
    section = text.split("## Headline", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] not in ("Arm", "---"):
            rows.append((cells[0], cells[1]))
        if rows and not line.startswith("|"):
            break
    return rows


def test_committed_chart_is_byte_identical_to_a_regeneration() -> None:
    regenerated = render_svg(RESULTS.read_text(encoding="utf-8")).encode("utf-8")
    assert regenerated == SVG.read_bytes()


def test_each_bar_carries_its_table_value() -> None:
    rows = _table_rows()
    assert len(rows) == 4
    bars = BAR.findall(SVG.read_text(encoding="utf-8"))
    assert [(arm, value) for arm, value, _ in bars] == rows
    for (_, value, height), (_, table_value) in zip(bars, rows):
        assert float(value) == float(table_value)
        assert abs(float(height) - float(table_value) * PLOT_H) < 0.01
