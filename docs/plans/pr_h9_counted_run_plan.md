# Pyx H9: counted run package (plan, no code)

Status: DRAFT plan for Ashutosh, revised against the frozen EVAL.md on main 66732ec (sha256 73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb). It implements that file exactly, including A1 to A11 and the five wording rulings. Base: main. Stacked branches: pyx/h9a-replay-reps, pyx/h9b-phase1, pyx/h9c-phase2.

## 1. Standing rules
A counted run follows the frozen EVAL.md and the approved plan exactly, runs only through committed and gated code, and never shrinks the protocol for credits. The pilot thin_20261102_r1 is a PILOT only.

## 2. What the frozen EVAL requires (section, then implementation)
- S3 and S4: three repetitions, distinct run ids `{RUN}_r0`, `_r1`, `_r2`. Tasks T1 clean and T2 clean, plus the T1 planted poison condition in the no memory arm. Held out tasks stay out; every claim is scoped to the training tasks; no parity margin. The commands accept no task list, so no held out task can enter.
- S6 A4, candidacy: candidates come from repetition 0 only. Repetitions 1 and 2 are distilled and their candidates written to `candidates_r1.jsonl` and `candidates_r2.jsonl` and reported, never replayed and never carried into any arm.
- S6 poison check: every repetition 0 candidate, against the copy it came from.
- S6 A1 and A2, paired replay: for each repetition 0 candidate with a poison pass, replay on its source and sibling in all three repetitions. Each repetition uses its own `without_runs` Paired baseline (H8): one empty context run per task per repetition, shared by all candidates in that repetition, never taken from cycle 0.
- S6 A2 and A3, the 2 of 3 rule: a lesson passes only if it fixes its criterion in at least 2 of 3 repetitions and breaks nothing in any. Inconclusive never counts as fixed or broken; an inconclusive repetition counts as not fixed (fixed, inconclusive, fixed passes; fixed plus two inconclusive fails).
- S7 A8, pairs: phase 1 presents the candidate list and Ashutosh names pairs. Their together runs happen in all three repetitions, against the same Paired baselines, inside phase 1 and before approval. A break in any repetition leaves the pair unresolved, neither lesson is carried, and the pair is reported in the run summary. Excluded lessons keep their replay rows.
- S6 approval: `python -m pyx.run approve` (H6) at Ashutosh's machine. The bot never types a decision.
- S5 arms, cycle 1, three repetitions:
  - No memory: empty.
  - Raw traces (A5): the same repetition's cycle 0 answer for the task and its failed criteria.
  - Free lessons (A6): all repetition 0 candidates, including poison check failures, training tasks only.
  - Earned lessons (A7): poison pass, replay pass under 2 of 3, HUMAN_APPROVED with matching hash, minus unresolved pairs. The same set in all three repetitions.
- S8 metrics and A10: conclusive criteria only; inconclusive, disagreement and Judge B malformed rates; self agreement across the three repetitions, cycle 0 per task and cycle 1 per arm and task.
- S9 bars: the planted earned listing, for Ashutosh's read against both variants.
- A9: two commands under one run id.
- S11 and A11: abort when new Meta spend passes $0.80 or new Baseten passes $2.50, on any budget stop, or on Ashutosh's planted read.

## 3. Commands (committed, gated)
```
python -m pyx.run phase1 --run-id ID --out DIR --eval-sha256 HEX --reps 3 [--pairs PATH] [--keyless]
python -m pyx.run phase2 --run-id ID --out DIR --eval-sha256 HEX --reps 3 [--keyless]
```
- Each refuses with exit 2 and writes nothing unless EVAL.md is frozen and matches `--eval-sha256`, and unless `--reps` equals the repetitions frozen in EVAL.md section 3 (parsed from "3 repetitions."). A mismatch cannot shrink the protocol.
- Phase 1 has two stops under one command name. The first invocation runs cycle 0, distill, the poison check and paired replay, writes `candidates_for_pairs.txt`, and exits 0 with "awaiting pairs". Ashutosh writes `pairs.txt` (one pair per line, or the single word none). Rerunning phase1 with `--pairs DIR/pairs.txt` resumes: every finished step is served from the answer store and call log (idempotent), the together runs execute, and phase 1 ends with "ready for approval".
- Phase 2 refuses with exit 3 until `pairs.txt` exists and every replay pass lesson outside an unresolved pair has an approval row. It then runs cycle 1 and writes `metrics.json`, `planted_earned.md` and `summary.md`.
- `--keyless` reruns either phase from DIR/calls.jsonl with keys unset and sockets blocked, and must reproduce every output byte for byte.
- Budget: the ledger is read before each call group. When a cap is passed, `abort.txt` is written and the command exits 4.

## 4. PR split (estimated total about 430 lines, so three stacked PRs)
| PR | Branch | Scope | Lines |
|---|---|---|---|
| H9a | pyx/h9a-replay-reps | `pyx/replay.py`: `replay_reps` (one lesson over three Paired baselines, giving one aggregate replay row plus per repetition detail rows in `replay_reps.tsv`) and `pair_reps` (together runs over three Paired baselines, giving a resolved or unresolved verdict). Tests. | about 130 |
| H9b | pyx/h9b-phase1 | `pyx/phase.py`: phase 1 and its CLI wiring in `pyx/run.py`, EVAL reps parsing, budget abort, resume with `--pairs`. Tests with fakes. | about 150 |
| H9c | pyx/h9c-phase2 | phase 2: arm contexts per A5 to A7, cycle 1, metrics, planted listing, summary; keyless for both phases. Tests with fakes. | about 150 |

## 5. Tests first (fakes only, no network)
H9a:
1. Fixed in 2 of 3 with nothing broken passes; fixed in 1 of 3 is NO_FIX.
2. Fixed, inconclusive, fixed passes; fixed plus two inconclusive fails as NO_FIX.
3. Broken in any one repetition is REGRESSION, even when fixed in all three.
4. Each repetition compares only with its own Paired baseline; a baseline from another repetition raises UnpairedBaselineError.
5. pair_reps: a together break in any repetition gives unresolved; none gives resolved; neither decides approval.
6. The aggregate row carries criteria_fixed and criteria_broken and a flag listing the per repetition outcomes.

H9b:
7. Draft EVAL, mismatched hash, or `--reps 1` gives exit 2 and writes nothing.
8. Call counts match section 6 exactly for the fake candidates.
9. Only repetition 0 candidates are replayed; repetition 1 and 2 candidates are written and reported, never replayed.
10. Replay never receives a cycle 0 report (it would raise UnpairedBaselineError).
11. The first invocation stops at "awaiting pairs"; the resume makes zero new calls for finished steps and runs together runs for named pairs only.
12. Passing a cap writes abort.txt and exits 4 with no further calls.

H9c:
13. Phase 2 exits 3 while pairs.txt is missing or an admissible lesson lacks an approval row.
14. Raw traces carries the same repetition's cycle 0 answer; free lessons carries every repetition 0 candidate including poison failures; earned is identical across the three repetitions and excludes unresolved pairs.
15. Metrics include self agreement per task (cycle 0) and per arm and task (cycle 1).
16. The planted listing contains exactly the earned lessons distilled from planted answers.
17. Keyless reruns of phase 1 and phase 2 reproduce every output byte for byte with no unused log lines.
18. No tracing import and no HTTP client in the phase module.

## 6. Call counts, spend and wall time
Assuming about 10 repetition 0 candidates with poison passes (as in the pilot) and one named pair:
- Cycle 0: 3 tasks times 3 repetitions = 9 answers.
- Distill: about 10 calls per repetition, so about 30 (repetitions 1 and 2 included, for the record).
- Replay: 10 candidates times 2 tasks times 3 repetitions = 60, plus 2 without runs times 3 = 6, so 66.
- Pair together runs: 2 tasks times 3 repetitions = 6 per pair.
- Cycle 1: 4 arms times 2 tasks times 3 repetitions = 24.
- Total: about 105 graded answers and about 30 distill calls.

Spend, from pilot unit costs ($0.00336 Meta and $0.0101 Baseten per graded answer, $0.00042 Meta per distill call): Meta about $0.37, Baseten about $1.06. This matches the frozen EVAL estimate ($0.37 and $1.08) and sits under the caps ($0.80 and $2.50). Ledger now: Meta $0.10897700, Baseten $0.35406425.

Wall time, from the pilot (about 45 s per graded answer, sequential):
- Phase 1 first stop: about 75 answers, about 56 minutes.
- Pair resume: about 6 answers per pair, about 5 minutes.
- Approval: Ashutosh's pause.
- Phase 2: 24 answers, about 18 minutes.
- About 80 minutes of execution in total, plus the two pauses.

Build: three gated PRs, roughly 30 to 45 minutes each to write and test.

## 7. Open questions with defaults
1. Pair naming inside "two commands". Default: phase1 stops at "awaiting pairs" and resumes under the same command with `--pairs`, so there are still two command names under one run id. Alternative: phase1 waits on stdin for pair names, which needs Ashutosh at the box.
2. Aggregate replay row. Default: one replay row in decisions.tsv per lesson, seed 0, run id `{RUN}_replay`, flags `reps=F,I,F` (fixed, inconclusive, not fixed), with per repetition detail in replay_reps.tsv.
3. Candidates with a poison failure. Default: not replayed (the admission chain stops them), but carried in the free lessons arm per A6.
4. Distilling repetitions 1 and 2. Default: yes, for the A4 record. This costs about $0.008 Meta. Alternative: skip distill there.
5. Duplicate lesson texts across repetitions. Default: the candidate store already skips identical texts; a repetition 1 or 2 text identical to a repetition 0 text is reported as seen again, not as a new candidate.
6. Parallelism. Default: sequential, as in the pilot, for clean logs and keyless order. Running tasks in parallel could roughly halve wall time, but needs a log ordering change.
7. Pacing tonight. Default: build H9a to H9c and gate them, then start phase 1 only on Ashutosh's go. At about 80 minutes of execution plus the pauses, a start after midnight runs into report day.
