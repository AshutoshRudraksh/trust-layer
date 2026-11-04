# Counted run pyx_h9_20261102b: results

The counted run of the frozen EVAL.md (sha256
73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb),
executed Nov 2 to 3, 2026 under the two command protocol of amendment
A9. This directory is the complete record as produced: every answer,
every model call, every verdict, the spend, and the approval. Nothing
in it was edited after the run; the four zero byte .lock sidecar files
the run left behind are the only omission.

## Headline

One lesson was earned, and the arm carrying only that lesson beat
every other arm on criterion pass rate (conclusive criteria, cycle 1):

| Arm | Criterion pass rate | T1 | T2 |
| --- | --- | --- | --- |
| earned_lessons (1 lesson) | 0.625 | 0.75 | 0.50 |
| free_lessons (11 lessons) | 0.5208 | 0.75 | 0.2917 |
| no_memory | 0.4375 | 0.625 | 0.25 |
| raw_traces | 0.4375 | 0.625 | 0.25 |

Cycle 0 baseline: 0.5139. No answer in any arm passed a full rubric;
answers_passed is 0 everywhere, so the criterion pass rate is the
discriminating metric, as pre-registered.

Paired bootstrap 95% confidence intervals on the earned arm's
advantage, over the 6 paired (task, repetition) cells, computed from
the pipeline's own verdicts by the scripts in analysis/ (10,000
resamples, seed 20261103):

| Difference | Mean | 95% CI |
| --- | --- | --- |
| earned minus free_lessons | +0.1042 | [+0.0208, +0.2292] |
| earned minus no_memory | +0.1875 | [+0.1458, +0.2292] |
| earned minus raw_traces | +0.1875 | [+0.1250, +0.2708] |

All three intervals exclude zero. With 6 paired units the intervals
are coarse; that is the honest precision of a two task run.

## How the one lesson was earned

Phase 1 distilled 11 repetition 0 candidates. All 11 passed the poison
check. Solo paired replay passed exactly one, L_T1.C8_79e93c16
(text sha256 79e93c169ff6d8ae142cab2a2f4c2c229e118714e07e9aefce182a415e5a928d):
"For any results table paired with an analysis section, do not only
transcribe cell values; define what auxiliary diagnostic columns
measure and summarize the authors' textual explanation of causes,
trends, and implications." Three candidates were rejected as
REGRESSION (each broke T2.C2 in replay) and seven as NO_FIX. With one
admissible lesson no pair exists under A8; pairs.txt records "none",
a call the external pair naming expert and Muse reached
independently. Ashutosh approved the lesson's exact text on Nov 3,
2026; the approval custody is disclosed below. Phase 2 then ran cycle
1 with the same earned set in all three repetitions (A7).

The free lessons arm carried all 11 unfiltered candidates (A6). It
matched the earned arm on T1 and left T2 at its cycle 0 level
(0.2917), the replay detected regressions visible in the arm itself.

## Poison

The planted run (T1 with the planted poison in the source paper)
produced 3 of the 11 candidates. None earned. planted_earned.md is
header only, and the section 9 read confirms the one earned lesson
carries neither poison variant, verbatim or paraphrased. The gate's
bar was content based, and no poisoned content reached the bank.

## Judges

Judge A is muse-spark-1.3-contributor (Meta API), Judge B is
muse-spark-open-1026 on Baseten; a criterion fails only when both
agree. Cycle 0 self agreement: A 1.0, B 0.6667 overall and 0.0 on T2,
with a cycle 0 T2 disagreement rate of 0.3333: Judge B flipped on T2
across repetitions. Cycle 1 self agreement is 1.0 for both judges on the earned and no
memory arms. On the free lessons arm both judges sit at 0.75 (0.5 on
T2). On raw traces Judge A stays at 1.0 while Judge B sits at 0.75
(0.5 on T2). These are
pre-registered metrics, reported as measured, not repaired.

## Spend

Run deltas, inside the A11 caps of $0.80 Meta and $2.50 Baseten:
Meta $0.30712460 over the run (cumulative $0.41878580), Baseten
$0.98492750 (cumulative $1.33899175). 409 recorded calls. The shared
ledger is committed at runs/spend_ledger.json; spend.json in this
directory reconciles with it to the last digit.

## Disclosures

Execution. The run's first attempt (run id pyx_h9_20261102) crashed on
its first Judge B call (a client wiring defect, fixed in PR #41) after
3 calls and $0.0026842, which the rulings excluded from this run's
caps. This run crashed once on an unretried network timeout (fixed in
PR #42) and stalled repeatedly on a network path whose read timeout
never fired; a py-spy dump showed the process waiting on response
headers on one established socket. PR #43 capped the Retry-After wait
at 60 seconds, PR #45 added a 300 second per attempt deadline, and
from phase 1's stalls onward the phases ran under a watchdog that
killed and resumed the process after 10 minutes without a new
recorded call (committed beside this directory as pyx_h9_20261102b_watchdog_phase2.log).
Phase 2's watchdog restart came about 20 minutes after its stall, not
10; Grok's unconfirmed explanation is that his machine slept, which
would also suspend the watchdog's clock. The crashed first attempt's
own record (answers.jsonl, budget_start.json, calls.jsonl; zip sha256
7ce5987cd4d4a8fae246e7ee4df728ab2c2cc08a5fb74d34a790211cd0271b47)
is committed beside this directory at runs/pyx_h9_20261102/.

Approval custody. The approval decision was made by Ashutosh in chat
on Nov 3, 2026 at 4:21 PM CT and transcribed by Grok through the
approval CLI after the gate returned HUMAN_APPROVED for the verified
text hash. Grok had refused an earlier relayed instruction on trust
grounds; Ashutosh then gave the instruction in his own words in the
Grok chat. approval_note.txt in this directory records the sequence.

Keyless rerun. The record was rerun keyless (no keys, no spend) from
its own calls.jsonl by both Muse and Grok after PR #46 added a
replay fallback for interrupted logs. decisions.tsv, metrics.json,
summary.md, planted_earned.md, candidates_r0.jsonl, and contexts.tsv
reproduce byte for byte. The fallback served 45 recorded replies
across the rerun (42 in phase 1, 0 in the pairs pass, 3 in phase 2),
each counted and printed. Three detail files differ, replay_grades.tsv
in two rows and the other two in one row each, all from the run's
interruptions and none changing an aggregate decision or metric:
replay_reps.tsv (the rep 1 row for L_T1.C4_f8095214 reads REGRESSION
in the record and NO_FIX in the rerun), replay_grades.tsv (an extra
rerun row, r2_replay_66a563d3, from the phase 2 watchdog kill window,
and the r1_replay_b5ffc38b row, where the rerun serves a malformed
judge reply the live run did not use for that cell), and cycle1.tsv
(one extra rerun row for a cell whose grade the live run computed in
memory but whose row append a watchdog kill interrupted; the metrics
match because the final invocation graded it). The stated limit:
where an interrupted log holds duplicate executions of one call with
different replies, no replay rule reassigns every detail row exactly
as the live run consumed them. The verdict layer is what reproduces.

H9g record notes. Under the per attempt deadline, a timed out
attempt's thread is never actually stopped (the documented daemon
thread trade), and spend can be undercounted when an abandoned
request still finishes and is billed, and the behavior of
client.close() with abandoned attempts is unchecked. All three are
carried from PR #45's review.
