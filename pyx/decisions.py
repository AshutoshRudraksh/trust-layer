"""Rows for decisions.tsv, the public log of every grade and verdict.

Columns are the ten from spec Section 4 in spec order, then two trailing
amendments: `flags` (JUDGE_DISAGREE, JUDGE_UNAVAILABLE) and `task_id` (which
task a grade row is about). Every specced column keeps its position. See
docs/decisions_tsv.md. Reason codes are the frozen six and nothing else; an
INCONCLUSIVE grade is written as result inconclusive with an empty reason code
and the flag JUDGE_UNAVAILABLE. Every row is validated when it is built.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import List

from pyx.checker import FAIL
from pyx.judges import INCONCLUSIVE, JUDGE_DISAGREE, JUDGE_UNAVAILABLE, GradeReport, JudgedVerdict

COLUMNS = ("lesson_id", "step", "result", "reason_code", "criteria_fixed", "criteria_broken",
           "judge_a", "judge_b", "seed", "run_id", "flags", "task_id")
REASON_CODES = frozenset({"UNTRUSTED_SOURCE", "NO_FIX", "REGRESSION", "JUDGE_DISAGREE",
                          "HUMAN_DENIED", "HUMAN_APPROVED"})
RESULTS = frozenset({"pass", "fail", "inconclusive"})
STEPS = frozenset({"poison", "replay", "approval", "grade"})


class DecisionRowError(ValueError):
    """A decisions.tsv row breaks the schema; the message names the column."""


@dataclass(frozen=True)
class DecisionRow:
    lesson_id: str
    step: str
    result: str
    reason_code: str
    criteria_fixed: str
    criteria_broken: str
    judge_a: str
    judge_b: str
    seed: str
    run_id: str
    flags: str
    task_id: str

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, str) or any(c in value for c in "\t\n\r"):
                raise DecisionRowError(f"{f.name}: must be a string with no tab or newline")
        if self.reason_code and self.reason_code not in REASON_CODES:
            raise DecisionRowError(f"reason_code: {self.reason_code!r} is not a frozen reason code")
        if self.result not in RESULTS:
            raise DecisionRowError(f"result: {self.result!r} is not one of {sorted(RESULTS)}")
        if self.step not in STEPS:
            raise DecisionRowError(f"step: {self.step!r} is not one of {sorted(STEPS)}")
        if self.result == "inconclusive" and (self.reason_code or JUDGE_UNAVAILABLE not in self.flags.split(",")):
            raise DecisionRowError("reason_code: an inconclusive row needs an empty reason code and the flag "
                                   "JUDGE_UNAVAILABLE")

    def values(self) -> List[str]:
        return [getattr(self, c) for c in COLUMNS]


def rows_from_grade(report: GradeReport, run_id: str, seed: int) -> List[DecisionRow]:
    """One grade row per graded answer."""
    judged = [v for v in report.verdicts if isinstance(v, JudgedVerdict)]
    broken = [v.criterion_id for v in report.verdicts if v.status == FAIL]
    flags = [f for f in (JUDGE_DISAGREE, JUDGE_UNAVAILABLE) if any(f in v.flags for v in judged)]
    if broken:
        result = "fail"
    elif any(v.status == INCONCLUSIVE for v in report.verdicts):
        result = "inconclusive"
    else:
        result = "pass"
    return [DecisionRow(
        lesson_id="", step="grade", result=result,
        reason_code=JUDGE_DISAGREE if JUDGE_DISAGREE in flags else "",
        criteria_fixed="", criteria_broken=",".join(broken),
        judge_a=",".join(f"{v.criterion_id}={v.judge_a.verdict}" for v in judged),
        judge_b=",".join(f"{v.criterion_id}={v.judge_b.verdict}" for v in judged),
        seed=str(seed), run_id=run_id, flags=",".join(flags), task_id=report.task_id,
    )]
