"""Causal replay (spec Section 5): rerun the source task and its siblings with the lesson, compare with the run without.

The caller supplies `run(task_id, context, run_id)`, which answers with the worker
and grades the answer. The baseline is a Paired value that only without_runs can
build: one run per task with an empty context in the same repetition (plan H line
70, EVAL.md section 6). A historical answer, such as cycle 0, cannot be passed. A lesson
passes when its own criterion goes from FAIL to PASS on its source task and no
criterion that passed without it fails with it, on any task. Only conclusive
statuses count: an inconclusive criterion is never fixed. Otherwise the row says
REGRESSION (something broke) or NO_FIX. Replay runs get their own run ids, so
their answers and rows never collide with the run they are compared against.
replay_pair records what each of two lessons fixes and breaks alone and together;
it decides nothing (the rule is frozen in EVAL.md).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from pyx.arms import ArmContext
from pyx.checker import FAIL, PASS
from pyx.decisions import DecisionRow
from pyx.lessons import Candidate

Run = Callable[[str, ArmContext, str], Any]
_BUILT_BY_WITHOUT_RUNS = object()


class UnpairedBaselineError(TypeError):
    """The baseline is not a paired run without the lesson from this repetition."""


@dataclass(frozen=True)
class Paired:
    run_id: str
    seed: int
    reports: Mapping[str, Any]
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _BUILT_BY_WITHOUT_RUNS:
            raise UnpairedBaselineError("a Paired baseline is built only by without_runs")


def without_runs(tasks: Sequence[str], run: Run, run_id: str, seed: int) -> Paired:
    ctx, rid = ArmContext("replay_without", "", ()), replay_run_id(run_id, ())
    return Paired(run_id, seed, {t: run(t, ctx, rid) for t in tasks}, _BUILT_BY_WITHOUT_RUNS)


def _check(baseline: Paired, run_id: str, seed: Optional[int] = None) -> Mapping[str, Any]:
    if not isinstance(baseline, Paired):
        raise UnpairedBaselineError(f"baseline must be Paired from without_runs, got {type(baseline).__name__}")
    if baseline.run_id != run_id or (seed is not None and baseline.seed != seed):
        raise UnpairedBaselineError(f"baseline is from {baseline.run_id} seed {baseline.seed}, not {run_id} seed {seed}")
    return baseline.reports


def replay_run_id(run_id: str, lesson_ids: Sequence[str]) -> str:
    return f"{run_id}_replay_{hashlib.sha256('+'.join(lesson_ids).encode()).hexdigest()[:8]}"


def _context(cands: Sequence[Candidate]) -> ArmContext:
    text = "\n".join(f"Lesson {c.lesson.lesson_id}: {c.lesson.text}" for c in cands)
    return ArmContext("replay", text, tuple(c.lesson.lesson_id for c in cands))


def _statuses(report: Any) -> Dict[str, str]:
    return {v.criterion_id: v.status for v in report.verdicts}


def _diff(without: Any, with_: Any) -> Tuple[List[str], List[str]]:
    before, after = _statuses(without), _statuses(with_)
    fixed = sorted(c for c, s in after.items() if s == PASS and before.get(c) == FAIL)
    broken = sorted(c for c, s in after.items() if s == FAIL and before.get(c) == PASS)
    return fixed, broken


def _run_with(cands: Sequence[Candidate], tasks: Sequence[str], run: Run, run_id: str) -> Dict[str, Any]:
    ctx = _context(cands)
    rid = replay_run_id(run_id, ctx.lesson_ids)
    return {t: run(t, ctx, rid) for t in tasks}


def replay_lesson(cand: Candidate, tasks: Sequence[str], run: Run, baseline: Paired,
                  run_id: str, seed: int, copy: str) -> DecisionRow:
    without = _check(baseline, run_id, seed)
    with_ = _run_with([cand], tasks, run, run_id)
    criterion = cand.lesson.fixes_criterion_id
    source = criterion.split(".")[0]
    fixed = criterion if criterion in _diff(without[source], with_[source])[0] else ""
    broken = sorted(c for t in tasks for c in _diff(without[t], with_[t])[1])
    result = "pass" if fixed and not broken else "fail"
    reason = "" if result == "pass" else ("REGRESSION" if broken else "NO_FIX")
    return DecisionRow(cand.lesson.lesson_id, "replay", result, reason, fixed, ",".join(broken), "", "",
                       str(seed), run_id, "", source, copy)


def replay_pair(a: Candidate, b: Candidate, tasks: Sequence[str], run: Run, baseline: Paired,
                run_id: str) -> Dict[str, Dict[str, Tuple[List[str], List[str]]]]:
    without = _check(baseline, run_id)
    table = {}
    for cands in ([a], [b], [a, b]):
        with_ = _run_with(cands, tasks, run, run_id)
        key = "+".join(c.lesson.lesson_id for c in cands)
        table[key] = {t: _diff(without[t], with_[t]) for t in tasks}
    return table
