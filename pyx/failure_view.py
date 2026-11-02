"""The failure view: what the distiller may know about a failed criterion.

This runs on the grading side. It reads the rubric as the checker role and
hands out only the task id, criterion id, criterion type, the source pointer in
the paper (such as "Table 1") and the paper id. Check text, expected values and
judge replies never leave here, so a lesson cannot carry a memorized number.
Only criteria whose final status is FAIL count: a split that passed with
JUDGE_DISAGREE and an INCONCLUSIVE criterion are not failures. A task that is
not a training task raises before anything is handed out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pyx.checker import FAIL
from pyx.judges import GradeReport
from pyx.rubric import load_rubric


class HeldOutTaskError(PermissionError):
    """The distiller never sees a held out task."""


@dataclass(frozen=True)
class FailedCriterion:
    task_id: str
    criterion_id: str
    type: str
    source: str
    paper_id: str


def failure_view(report: GradeReport) -> List[FailedCriterion]:
    rubric = load_rubric(report.task_id, role="checker")
    if rubric.get("split") != "training":
        raise HeldOutTaskError(f"{report.task_id} is not a training task; the distiller never sees it")
    by_id = {c["id"]: c for c in rubric["criteria"]}
    return [FailedCriterion(report.task_id, v.criterion_id, by_id[v.criterion_id]["type"],
                            by_id[v.criterion_id]["source"], rubric["paper"])
            for v in report.verdicts if v.status == FAIL]
