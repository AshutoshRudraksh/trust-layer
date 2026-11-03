"""PR H9a tests: replay over three repetitions (EVAL.md section 6, A1 to A3) and pair together runs (A8). Fakes only."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pyx.lessons import CandidateStore
from pyx.replay import UnpairedBaselineError, pair_reps, replay_reps, without_runs

CANDS = CandidateStore(Path(__file__).resolve().parent / "fixtures" / "pyx" / "replay" /
                       "e4_distill_candidates.jsonl").read()
L1, L6 = CANDS[0], CANDS[5]  # L1 fixes T1.C1
LID = L1.lesson.lesson_id
BASE = {"T1": {"T1.C1": "FAIL", "T1.C2": "PASS"}, "T2": {"T2.C1": "FAIL", "T2.C7": "PASS"}}


def _report(statuses):
    return NS(verdicts=tuple(NS(criterion_id=c, status=s) for c, s in statuses.items()))


class Runner:
    """Outcome per (lesson ids, task, repetition); the repetition is read from the run id."""

    def __init__(self, outcomes=None):
        self.outcomes, self.calls = outcomes or {}, []

    def __call__(self, task_id, ctx, run_id):
        rep = int(run_id.split("_r")[1][0])
        self.calls.append((task_id, ctx.lesson_ids, run_id))
        return _report(self.outcomes.get((ctx.lesson_ids, task_id, rep), BASE[task_id]))


def _baselines(run, run_id="R"):
    return [without_runs(["T1", "T2"], run, f"{run_id}_r{i}", i) for i in range(3)]


def _with(t1_by_rep, t2=None):
    out = {}
    for rep, status in enumerate(t1_by_rep):
        out[((LID,), "T1", rep)] = dict(BASE["T1"], **{"T1.C1": status})
        if t2 and t2[rep]:
            out[((LID,), "T2", rep)] = dict(BASE["T2"], **t2[rep])
    return out


def _replay(t1_by_rep, t2=None):
    run = Runner(_with(t1_by_rep, t2))
    return replay_reps(L1, ["T1", "T2"], run, _baselines(run), "R", "clean")


def test_fixed_in_two_of_three_with_nothing_broken_passes_and_one_of_three_is_no_fix() -> None:
    row, detail = _replay(["PASS", "FAIL", "PASS"])
    assert (row.step, row.result, row.reason_code, row.criteria_fixed, row.criteria_broken) == \
        ("replay", "pass", "", "T1.C1", "")
    assert len(detail) == 3 and [d.seed for d in detail] == ["0", "1", "2"]
    row, _ = _replay(["PASS", "FAIL", "FAIL"])
    assert (row.result, row.reason_code, row.criteria_fixed) == ("fail", "NO_FIX", "")


def test_an_inconclusive_repetition_counts_as_not_fixed() -> None:
    row, _ = _replay(["PASS", "INCONCLUSIVE", "PASS"])
    assert (row.result, row.flags) == ("pass", "reps=F,I,F")
    row, _ = _replay(["PASS", "INCONCLUSIVE", "INCONCLUSIVE"])
    assert (row.result, row.reason_code, row.flags) == ("fail", "NO_FIX", "reps=F,I,I")


def test_a_break_in_any_one_repetition_is_regression_even_when_fixed_in_all_three() -> None:
    row, _ = _replay(["PASS", "PASS", "PASS"], t2=[None, {"T2.C7": "FAIL"}, None])
    assert (row.result, row.reason_code, row.criteria_fixed, row.criteria_broken) == \
        ("fail", "REGRESSION", "T1.C1", "T2.C7")


def test_each_repetition_compares_only_with_its_own_paired_baseline() -> None:
    run = Runner()
    b = _baselines(run)
    with pytest.raises(UnpairedBaselineError):
        replay_reps(L1, ["T1", "T2"], run, [b[0], b[2], b[1]], "R", "clean")
    with pytest.raises(UnpairedBaselineError):
        replay_reps(L1, ["T1", "T2"], run, b[:2], "R", "clean")
    with pytest.raises(UnpairedBaselineError):
        replay_reps(L1, ["T1", "T2"], run, [{"T1": None}] * 3, "R", "clean")


def test_pair_together_runs_repeat_three_times_and_any_break_leaves_the_pair_unresolved() -> None:
    ids = (L1.lesson.lesson_id, L6.lesson.lesson_id)
    clean = Runner()
    verdict = pair_reps(L1, L6, ["T1", "T2"], clean, _baselines(clean), "R")
    assert verdict["resolved"] is True and len(verdict["together"]) == 3
    assert {c[1] for c in clean.calls if c[1]} == {ids} and len([c for c in clean.calls if c[1]]) == 6
    broke = Runner({(ids, "T2", 2): dict(BASE["T2"], **{"T2.C7": "FAIL"})})
    verdict = pair_reps(L1, L6, ["T1", "T2"], broke, _baselines(broke), "R")
    assert verdict["resolved"] is False and verdict["together"][2]["T2"] == ([], ["T2.C7"])


def test_the_aggregate_row_names_the_run_and_flags_each_repetition() -> None:
    row, detail = _replay(["PASS", "FAIL", "PASS"])
    assert (row.seed, row.run_id, row.flags, row.task_id, row.copy) == ("0", "R_replay", "reps=F,N,F", "T1", "clean")
    assert [d.run_id for d in detail] == ["R_r0", "R_r1", "R_r2"]
