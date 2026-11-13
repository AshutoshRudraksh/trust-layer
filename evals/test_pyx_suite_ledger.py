"""Hardening ticket 5: the counted ledger in CI (ADR 0005, item 3).

Two checks run on every PR through pytest: no long or short dash in the repo's own prose, and the
suite count stated in README.md equals what pytest collects. Frozen run records (runs/), EVAL.md,
and the quoted source papers (pyx/tasks/) are outside the dash check: they are not edited.
"""
from __future__ import annotations

from pathlib import Path

from pyx.suite_ledger import collected_count, dash_hits, prose_files, readme_count

ROOT = Path(__file__).resolve().parent.parent


def test_dash_hits_finds_long_and_short_dashes_with_line_numbers(tmp_path) -> None:
    f = tmp_path / "a.md"
    f.write_text("fine line\nbad \u2014 line\nalso \u2013 bad\nhyphen-ok\n", encoding="utf-8")
    assert dash_hits([f]) == [(f, 2), (f, 3)]


def test_prose_files_skip_frozen_and_quoted_sources() -> None:
    rel = {p.relative_to(ROOT).as_posix() for p in prose_files(ROOT)}
    assert "README.md" in rel
    assert "docs/specs/step1-consumer-agent.md" in rel
    assert not any(r.startswith(("runs/", "pyx/tasks/")) or r == "EVAL.md" for r in rel)


def test_readme_count_reads_the_stated_suite_size() -> None:
    assert readme_count("x\nThe suite collects 12 tests (`pytest --collect-only -q`).\ny") == 12
    assert readme_count("no count here") is None


def test_collected_count_parses_pytest_output() -> None:
    assert collected_count("a\nb\n344 tests collected in 0.35s\n") == 344


def test_repo_prose_has_no_long_or_short_dash() -> None:
    assert dash_hits(prose_files(ROOT)) == []


def test_readme_suite_count_matches_what_pytest_collects() -> None:
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert readme_count((ROOT / "README.md").read_text(encoding="utf-8")) == collected_count(out)
