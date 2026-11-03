"""PR H2 and H8 tests: causal replay against a paired run without the lesson in the same repetition. Fakes only."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

from pyx.lessons import CandidateStore
import pytest

from pyx.replay import Paired, UnpairedBaselineError, replay_lesson, replay_pair, replay_run_id, without_runs

CANDS = CandidateStore(Path(__file__).resolve().parent / "fixtures" / "pyx" / "replay" /
                       "e4_distill_candidates.jsonl").read()
L1 = CANDS[0]  # fixes T1.C1
BASE = {"T1": {"T1.C1": "FAIL", "T1.C2": "PASS", "T1.C8": "FAIL"}, "T2": {"T2.C1": "FAIL", "T2.C2": "PASS"}}


def _report(statuses):
    return NS(verdicts=tuple(NS(criterion_id=c, status=s) for c, s in statuses.items()))


class Runner:
    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []

    def __call__(self, task_id, ctx, run_id):
        self.calls.append((task_id, ctx, run_id))
        return _report(self.outcomes.get((ctx.lesson_ids, task_id), BASE.get(task_id)))


def _baseline(run=None, run_id="r1", seed=0):
    return without_runs(["T1", "T2"], run or Runner({}), run_id, seed)


def test_a_lesson_that_fixes_and_breaks_nothing_passes() -> None:
    run = Runner({((L1.lesson.lesson_id,), "T1"): dict(BASE["T1"], **{"T1.C1": "PASS"}),
                  ((L1.lesson.lesson_id,), "T2"): BASE["T2"]})
    row = replay_lesson(L1, ["T1", "T2"], run, _baseline(), "r1", 0, "clean")
    assert (row.step, row.result, row.reason_code, row.criteria_fixed, row.criteria_broken) == \
        ("replay", "pass", "", "T1.C1", "")
    assert (row.lesson_id, row.task_id, row.copy, row.run_id) == (L1.lesson.lesson_id, "T1", "clean", "r1")
    assert [c[1].text for c in run.calls] == [f"Lesson {L1.lesson.lesson_id}: {L1.lesson.text}"] * 2


def test_not_fixed_is_no_fix() -> None:
    run = Runner({((L1.lesson.lesson_id,), "T1"): BASE["T1"], ((L1.lesson.lesson_id,), "T2"): BASE["T2"]})
    row = replay_lesson(L1, ["T1", "T2"], run, _baseline(), "r1", 0, "clean")
    assert (row.result, row.reason_code, row.criteria_fixed) == ("fail", "NO_FIX", "")


def test_a_break_on_the_sibling_is_regression_even_when_fixed() -> None:
    run = Runner({((L1.lesson.lesson_id,), "T1"): dict(BASE["T1"], **{"T1.C1": "PASS"}),
                  ((L1.lesson.lesson_id,), "T2"): dict(BASE["T2"], **{"T2.C2": "FAIL"})})
    row = replay_lesson(L1, ["T1", "T2"], run, _baseline(), "r1", 0, "clean")
    assert (row.result, row.reason_code, row.criteria_fixed, row.criteria_broken) == \
        ("fail", "REGRESSION", "T1.C1", "T2.C2")


def test_an_inconclusive_criterion_never_counts_as_fixed() -> None:
    run = Runner({((L1.lesson.lesson_id,), "T1"): dict(BASE["T1"], **{"T1.C1": "INCONCLUSIVE"}),
                  ((L1.lesson.lesson_id,), "T2"): BASE["T2"]})
    assert replay_lesson(L1, ["T1", "T2"], run, _baseline(), "r1", 0, "clean").reason_code == "NO_FIX"


def test_replay_runs_get_their_own_run_ids() -> None:
    run = Runner({((L1.lesson.lesson_id,), t): BASE[t] for t in BASE})
    replay_lesson(L1, ["T1", "T2"], run, _baseline(), "r1", 0, "clean")
    assert {c[2] for c in run.calls} == {replay_run_id("r1", (L1.lesson.lesson_id,))} != {"r1"}
    assert replay_run_id("r1", ("a",)) != replay_run_id("r1", ("b",)) != replay_run_id("r1", ("a", "b"))


def test_pair_replay_records_alone_alone_and_together_without_deciding() -> None:
    a, b = CANDS[0], CANDS[5]
    ids = a.lesson.lesson_id, b.lesson.lesson_id
    out = {}
    for key in [(ids[0],), (ids[1],), ids]:
        out[(key, "T1")] = dict(BASE["T1"], **{"T1.C1": "PASS" if key != (ids[1],) else "FAIL"})
        out[(key, "T2")] = dict(BASE["T2"], **{"T2.C2": "FAIL" if key == ids else "PASS"})
    table = replay_pair(a, b, ["T1", "T2"], Runner(out), _baseline(), "r1")
    assert table[ids[0]]["T1"] == (["T1.C1"], []) and table[ids[1]]["T1"] == ([], [])
    assert table["+".join(ids)]["T2"] == ([], ["T2.C2"])
    assert set(table) == {ids[0], ids[1], "+".join(ids)}


def test_without_runs_run_each_task_once_with_an_empty_context_in_the_same_repetition() -> None:
    run = Runner({})
    paired = without_runs(["T1", "T2"], run, "r1", 2)
    assert [c[0] for c in run.calls] == ["T1", "T2"]
    assert {(c[1].arm, c[1].text, c[1].lesson_ids) for c in run.calls} == {("replay_without", "", ())}
    assert {c[2] for c in run.calls} == {replay_run_id("r1", ())} != {"r1"}
    assert (paired.run_id, paired.seed) == ("r1", 2)


def test_cycle0_pass_with_paired_fail_on_t2_c7_is_not_a_regression() -> None:
    cycle0_t2 = {"T2.C1": "FAIL", "T2.C7": "PASS"}  # the single historical answer: never consulted
    assert cycle0_t2["T2.C7"] == "PASS"
    paired = _baseline(Runner({((), "T1"): BASE["T1"], ((), "T2"): {"T2.C1": "FAIL", "T2.C7": "FAIL"}}))
    run = Runner({((L1.lesson.lesson_id,), "T1"): dict(BASE["T1"], **{"T1.C1": "PASS"}),
                  ((L1.lesson.lesson_id,), "T2"): {"T2.C1": "FAIL", "T2.C7": "FAIL"}})
    row = replay_lesson(L1, ["T1", "T2"], run, paired, "r1", 0, "clean")
    assert (row.result, row.reason_code, row.criteria_broken) == ("pass", "", "")


def test_paired_pass_with_lesson_fail_on_t2_c7_is_a_regression() -> None:
    paired = _baseline(Runner({((), "T1"): BASE["T1"], ((), "T2"): {"T2.C1": "FAIL", "T2.C7": "PASS"}}))
    run = Runner({((L1.lesson.lesson_id,), "T1"): dict(BASE["T1"], **{"T1.C1": "PASS"}),
                  ((L1.lesson.lesson_id,), "T2"): {"T2.C1": "FAIL", "T2.C7": "FAIL"}})
    row = replay_lesson(L1, ["T1", "T2"], run, paired, "r1", 0, "clean")
    assert (row.result, row.reason_code, row.criteria_broken) == ("fail", "REGRESSION", "T2.C7")


def test_a_historical_baseline_cannot_be_passed_or_built() -> None:
    historical = {t: _report(s) for t, s in BASE.items()}
    run = Runner({})
    with pytest.raises(UnpairedBaselineError):
        replay_lesson(L1, ["T1", "T2"], run, historical, "r1", 0, "clean")
    with pytest.raises(UnpairedBaselineError):
        replay_pair(CANDS[0], CANDS[5], ["T1", "T2"], run, historical, "r1")
    with pytest.raises(UnpairedBaselineError):
        Paired("r1", 0, historical)
    assert run.calls == []


@pytest.mark.parametrize("run_id,seed", [("r2", 0), ("r1", 1)])
def test_a_paired_baseline_from_another_repetition_is_refused(run_id, seed) -> None:
    paired, run = _baseline(), Runner({})
    with pytest.raises(UnpairedBaselineError):
        replay_lesson(L1, ["T1", "T2"], run, paired, run_id, seed, "clean")
    assert run.calls == []


def test_recorded_replay_reproduces_rows_with_no_unused_entries() -> None:
    outcomes = {((L1.lesson.lesson_id,), "T1"): dict(BASE["T1"], **{"T1.C1": "PASS"})}
    log = {}

    class Recorder(Runner):
        def __call__(self, task_id, ctx, run_id):
            rep = super().__call__(task_id, ctx, run_id)
            log[(task_id, ctx.text, run_id)] = rep
            return rep

    class Replayer:
        def __init__(self):
            self.served = set()

        def __call__(self, task_id, ctx, run_id):
            key = (task_id, ctx.text, run_id)
            self.served.add(key)
            return log[key]

    live_run = Recorder(outcomes)
    live = replay_lesson(L1, ["T1", "T2"], live_run, _baseline(live_run), "r1", 0, "clean")
    again_run = Replayer()
    again = replay_lesson(L1, ["T1", "T2"], again_run, _baseline(again_run), "r1", 0, "clean")
    assert again.values() == live.values() and again_run.served == set(log)
