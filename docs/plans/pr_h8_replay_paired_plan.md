# Pyx H8: paired replay in the same repetition (plan, no code)

Status: DRAFT plan for Ashutosh. Base: main b49a0ff (or main after PR #34). Branch: pyx/h8-replay-paired.

## 1. Finding
The plan and EVAL.md require replay to compare each lesson run with a run without the lesson in the same repetition.
- H plan, docs/plans/pr_h_runner_plan.md line 70: "rerun the worker on its source task and its sibling (the other training task) with the lesson as the only context, and once without it in the same repetition; grade both. Pass when the source criterion goes from fail to pass and no criterion that passed without the lesson fails with it."
- H plan line 15 (spec Section 5): "Rerun the source task plus siblings with and without the lesson".
- EVAL.md line 33: "Causal replay: the lesson alone in context, on its source task and its sibling, against a run without it."

The committed code does not produce that run. `pyx/replay.py` line 52, `replay_lesson(cand, tasks, run, without, run_id, seed, copy)`, takes `without` as a caller supplied mapping. Lines 57 and 58 diff against `without[source]` and `without[t]`. Line 65, `replay_pair`, does the same. Nothing in `pyx/replay.py` or `pyx/run.py` runs the worker without the lesson. Which baseline is used is left to the caller, and no committed caller exists.

The pilot driver passed the cycle 0 answers (scripts/pilot/thin_run.py: `without = {a.task_id: r for a, r in zip(answers, reports) if a.copy == "clean"}`). So the pilot's REGRESSION verdicts were judged against a single historical cycle 0 answer, not a paired run. Every one of the 9 pilot REGRESSION rows breaks T2.C7, and T2.C7 passed only in that one cycle 0 answer. That is the noise the paired design exists to remove.

## 2. Fix (scoped)
- `pyx/replay.py`: add `without_runs(tasks, run, run_id, seed)`. It runs each task once with an empty context under arm `replay_without` and run id `replay_run_id(run_id, [])`, then returns the reports keyed by task.
- Change `replay_lesson` and `replay_pair` to accept only a `Paired` value, a small frozen dataclass of (run_id, seed, reports) built by `without_runs`. Each checks that its run_id and seed are the ones the paired value carries, and raises `UnpairedBaselineError` otherwise. A plain dict of historical reports can no longer be passed.
- One without run per task per repetition, shared by every candidate in that repetition, as plan line 70 and the call counts in plan section 8 already assume ("plus one run without a lesson per task").
- No change to grading, distill, poison or approval.

## 3. Tests first (evals/test_pyx_replay.py, extended; fakes only)
1. `without_runs` calls the run callable once per task with an empty context, arm `replay_without`, and a replay run id distinct from wake ids.
2. A fake where the cycle 0 report passes T2.C7 but the paired without run fails it: the lesson run failing T2.C7 is not a REGRESSION.
3. A fake where the paired without run passes T2.C7 and the lesson run fails it: REGRESSION with criteria_broken T2.C7.
4. Passing a plain dict, or a Paired value from another run id or seed, raises UnpairedBaselineError and writes nothing.
5. `replay_pair` uses the same Paired value for alone, alone and together.
6. Keyless: a recorded fake log replays the without runs and the lesson runs byte for byte, with no unused lines.
7. The existing six replay tests are updated to build their baseline through `without_runs`.

## 4. Size
About 110 lines: tests about 70, code about 40.

## 5. Open questions with defaults
1. Without runs per repetition. Default: one per task per repetition, shared by all candidates in that repetition.
2. Should replay of the same candidate repeat across repetitions? Default: no change here; the counted run package (amendment A2) settles it.
