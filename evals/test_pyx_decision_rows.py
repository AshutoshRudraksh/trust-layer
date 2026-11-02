"""PR D2a tests: decisions.tsv row model, frozen reason codes and rows_from_grade. Pure, no file I/O."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pyx.decisions import COLUMNS, REASON_CODES, DecisionRow, DecisionRowError, rows_from_grade
from pyx.judges import grade_answer

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pyx"
SPEC_COLUMNS = ["lesson_id", "step", "result", "reason_code", "criteria_fixed", "criteria_broken",
                "judge_a", "judge_b", "seed", "run_id"]
BASE = DecisionRow(lesson_id="", step="grade", result="pass", reason_code="", criteria_fixed="",
                   criteria_broken="", judge_a="T1.C8=PASS", judge_b="T1.C8=PASS", seed="0", run_id="r1",
                   flags="", task_id="T1")


def test_columns_are_the_spec_columns_then_the_two_trailing_amendments() -> None:
    assert list(COLUMNS) == SPEC_COLUMNS + ["flags", "task_id"]


@pytest.mark.parametrize("code", sorted(REASON_CODES))
def test_each_frozen_code_is_accepted(code: str) -> None:
    assert replace(BASE, reason_code=code).reason_code == code


def test_the_frozen_list_is_exactly_six() -> None:
    assert REASON_CODES == {"UNTRUSTED_SOURCE", "NO_FIX", "REGRESSION", "JUDGE_DISAGREE",
                            "HUMAN_DENIED", "HUMAN_APPROVED"}


@pytest.mark.parametrize("code", ["INCONCLUSIVE", "JUDGE_UNAVAILABLE", "judge_disagree", "OTHER"])
def test_any_other_reason_code_raises(code: str) -> None:
    with pytest.raises(DecisionRowError, match="reason_code"):
        replace(BASE, reason_code=code)


@pytest.mark.parametrize("field,value", [("result", "maybe"), ("step", "distill")])
def test_result_and_step_are_closed_sets(field: str, value: str) -> None:
    with pytest.raises(DecisionRowError, match=field):
        replace(BASE, **{field: value})


def test_inconclusive_needs_empty_reason_and_the_unavailable_flag() -> None:
    ok = replace(BASE, result="inconclusive", flags="JUDGE_UNAVAILABLE")
    assert ok.result == "inconclusive"
    with pytest.raises(DecisionRowError):
        replace(ok, reason_code="JUDGE_DISAGREE")
    with pytest.raises(DecisionRowError):
        replace(ok, flags="")


@pytest.mark.parametrize("bad", ["a\tb", "a\nb", "a\rb"])
def test_tabs_and_newlines_are_refused_by_column(bad: str) -> None:
    with pytest.raises(DecisionRowError, match="judge_a"):
        replace(BASE, judge_a=bad)


class _Reply:
    def __init__(self, text: str) -> None:
        self.output_text, self.input_tokens, self.output_tokens, self.cost_usd = text, 1, 1, 0.0


class _Judge:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)

    def respond(self, prompt: str, **kw) -> _Reply:
        return _Reply(self.replies.pop(0))

    chat = respond


def _row(fixture: str, a, b) -> DecisionRow:
    report = grade_answer((FIXTURES / f"{fixture}.md").read_text(), fixture[:2], a, b)
    rows = rows_from_grade(report, run_id="runX", seed=3)
    assert len(rows) == 1
    return rows[0]


def test_all_pass() -> None:
    row = _row("T1_good", _Judge("PASS"), _Judge("PASS"))
    assert (row.result, row.reason_code, row.flags, row.criteria_broken) == ("pass", "", "", "")
    assert (row.step, row.lesson_id, row.task_id, row.run_id, row.seed) == ("grade", "", "T1", "runX", "3")
    assert (row.judge_a, row.judge_b, row.criteria_fixed) == ("T1.C8=PASS", "T1.C8=PASS", "")


def test_failing_programmatic_criteria_are_listed() -> None:
    row = _row("T1_bad", _Judge("FAIL"), _Judge("FAIL"))
    assert row.result == "fail"
    assert row.criteria_broken == "T1.C1,T1.C3,T1.C6,T1.C8"


def test_split_passes_with_judge_disagree() -> None:
    row = _row("T1_good", _Judge("FAIL"), _Judge("PASS"))
    assert (row.result, row.reason_code, row.flags) == ("pass", "JUDGE_DISAGREE", "JUDGE_DISAGREE")
    assert (row.judge_a, row.judge_b) == ("T1.C8=FAIL", "T1.C8=PASS")


def test_broken_judge_is_inconclusive_and_written_as_is() -> None:
    row = _row("T1_good", _Judge("PASS"), _Judge("huh", "still huh"))
    assert (row.result, row.reason_code, row.flags) == ("inconclusive", "", "JUDGE_UNAVAILABLE")
    assert row.judge_b == "T1.C8=MALFORMED"


def test_fail_beats_inconclusive() -> None:
    row = _row("T1_bad", _Judge("FAIL"), _Judge("huh", "still huh"))
    assert row.result == "fail" and row.flags == "JUDGE_UNAVAILABLE" and row.reason_code == ""
