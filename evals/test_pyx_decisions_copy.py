"""PR G2b tests: decisions.tsv column 13, `copy`, the paper copy a row is about (clean or planted)."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pyx.decisions import COLUMNS, DecisionLog, DecisionRow, DecisionRowError, rows_from_grade
from pyx.judges import grade_answer

ROW = DecisionRow(lesson_id="", step="grade", result="fail", reason_code="", criteria_fixed="",
                  criteria_broken="T1.C1", judge_a="T1.C8=FAIL", judge_b="T1.C8=FAIL", seed="0", run_id="r1",
                  flags="", task_id="T1", copy="clean")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pyx"


def test_clean_and_planted_rows_with_otherwise_identical_content_are_both_kept(tmp_path: Path) -> None:
    path = tmp_path / "decisions.tsv"
    planted = replace(ROW, copy="planted")
    assert DecisionLog(path).append([ROW, planted]) == 2
    assert DecisionLog(path).read() == [ROW, planted]


@pytest.mark.parametrize("value", ["dirty", "Clean", "clean,planted", " planted"])
def test_copy_outside_clean_and_planted_is_refused(value: str) -> None:
    with pytest.raises(DecisionRowError, match="copy"):
        replace(ROW, copy=value)


def test_copy_is_trailing_column_13_and_empty_means_no_paper_copy() -> None:
    assert COLUMNS.index("copy") == 12 == len(COLUMNS) - 1
    assert replace(ROW, copy="").copy == ""


def test_rows_from_grade_carries_the_copy() -> None:
    from evals.test_pyx_decision_rows import _Judge
    report = grade_answer((FIXTURES / "T1_good.md").read_text(), "T1", _Judge("PASS"), _Judge("PASS"))
    assert rows_from_grade(report, run_id="r1", seed=0, copy="planted")[0].copy == "planted"
    assert rows_from_grade(report, run_id="r1", seed=0)[0].copy == ""
