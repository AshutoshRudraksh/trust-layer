# PR H9h plan: a replay fallback so an interrupted run's log stays a complete recipe

Status: proposed by Muse under the Nov 3, 2026 seat split. Grok commits
verbatim and reviews as critic; Ashutosh approves and merges. Ruled Nov 3,
2026 as fix work that gates the counted run record and all submission work.
This plan is the second design; the first is recorded at the end because
the suite caught it and the reasoning is part of the record.

## Why

Verified firsthand on the counted run's record: the keyless rerun of
phase 1 runs out of call log entries at a cycle 0 worker call. The exact
mechanism, established by reading the engine and the log together: the
worker prompt for a task is identical across the three repetitions, and
LogFirst always tries the recorded log before calling live. The live
run's stage 1 was interrupted mid way; on resume, the re-walk found the
first two repetitions' answers already stored, and for the third
repetition's fresh cell it re-served a reply recorded for an earlier
repetition (same prompt, so the same reply the sequence needed), without
appending a line. The log faithfully holds the two live executions; the
rerun performs three serves and runs out. The pilot, never interrupted,
reruns byte identically. The counted run's results are unaffected (every
answer, grade, and decision is real and cross checked); what is missing
is a rerun rule that matches how the live engine itself behaves.

## What changes

Two seams, both gated to keyless reruns only, so live behavior is bit for
bit what it was:

- pyx/replay_client.py: when a keyless ReplayClient has no unused line
  for a requested key, it falls back to the most recent line with that
  key instead of raising: it returns that line's recorded reply, or
  re-raises its recorded error, exactly as a live re-serve through
  LogFirst would. LogFirst enables the fallback only when it has no live
  client. A key with no line at all still raises ReplayMissError, so a
  genuinely novel call in a rerun is still detected and still stops the
  rerun.
- pyx/phase.py, Engine._grade: the checker seam has the same consumption
  shape and the same interrupted run deficit. In keyless mode, when no
  unused checker line matches an answer, the engine reuses a matching
  recorded line, but only after _check_against_log revalidates it in
  full: checker code hash, rubric hash, answer hash, and every verdict
  recomputed and compared. A mismatch still raises. In live mode the
  engine keeps appending a fresh checker line on a re-grade, as today.
- Soundness: a replay key is a hash of judge, model, endpoint, prompt,
  and params, so the fallback can only ever return a recorded reply to
  the identical call, and it fires only when the sequence asks for that
  call more times than the run executed it live, which is precisely the
  interrupted run case, where the live run itself answered the extra
  serve from the same recorded reply.
- Nothing else changes: no live path is touched, verdicts and spend are
  untouched (a rerun's accounting already comes from the lines it
  serves), the frozen EVAL is untouched, and an uninterrupted run's
  rerun is bit for bit the old behavior, because the fallback never
  fires when the counts match.

## Tests first

New file evals/test_pyx_replay_fallback.py:

1. A log holding two lines for one key serves the same call three times;
   the third serve returns the most recent line's reply.
2. A log holding one error line for a key re-raises that recorded error
   on the over-serve, mirroring a live re-serve.
3. A key with no line at all still raises ReplayMissError.
4. The existing rerun invariant stands guard over the design:
   test_keyless_reruns_reproduce_every_output_byte_for_byte_with_no_unused_lines
   must pass unchanged, proving the fallback never fires and no line is
   left unused for an uninterrupted run.

## The counted run's proof, outside this PR

With the fallback merged, the counted run's own calls.jsonl, pristine
and unmodified, feeds the full keyless rerun of both phases for its
record PR: no derived log is needed any more. The comparison that
carries the proof, executed by Muse in the authoring run before this
package shipped: decisions.tsv, metrics.json, summary.md,
planted_earned.md, and candidates_r0.jsonl all reproduce byte for
byte. Two per repetition detail files differ in exactly one row each,
and both diffs are disclosed in the record: one replay detail row
(NO_FIX in the rerun where the live record says REGRESSION for the
same lesson and repetition; both fail the lesson and the aggregate
decision is identical), which traces to duplicate judge executions
with drifting replies in the interrupted log, and one cycle 1 grade
row present in the rerun but missing from the live file, where a
watchdog kill landed between that cell's answer and its row append
while the final re-walk still computed the metrics from it, which is
why the metrics match.

## Live test

- Fresh clone of the PR head: the full suite passes (332 baseline plus
  the 3 new tests; the fourth test above already exists) and check-eval
  exits 0 with the frozen hash.
- The authoring run executes the same numbers in the build clone before
  the package ships.

## The first design, and why the suite rejected it

The first design stamped every live re-serve into the log
(served_from_log lines at zero cost). The full suite caught it: the
existing rerun invariant failed, because a live phase 2 routinely
re-serves recorded calls while re-deriving its baselines, and the
keyless phase 2 derives the same state from its regenerated files
without repeating those serves. The stamps were left permanently
unused, 102 of them in the test flow, breaking the invariant from the
other direction. The lesson the design now follows: the asymmetry lives
in how often each side serves, not in missing executions, so the fix
belongs in the replay rule, not in the log.
