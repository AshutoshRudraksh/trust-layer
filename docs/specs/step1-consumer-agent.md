# Step 1 spec: a second agent that consumes the lesson bank over MCP, with gated write back

Status: draft for Ashutosh. Ticket 1 is implemented in the PR that adds this file. Tickets 2 onward wait on the open decisions below.

## 1. Problem

Pyx produces a bank of earned lessons, but nothing outside the pipeline reads it. Its beneficiary is other software, and today no other software is shown using it. Step 1 gives the bank a visible consumer: a second agent that reads earned lessons live over the existing MCP server, uses them on a task, and can send a lesson it learns back toward the bank only through the human exact text gate.

The read path had a hole that must close first. `get_lesson_provenance` served the full text of any candidate in the run, so a consumer could pull the text of rejected or planted lessons by id. Verified on runs/pyx_h9_20261102b before the fix: calling the tool for the planted candidate L_T1.C1_9dd514bb returned its full lesson text.

## 2. Settled facts this spec builds on

These come from runs/pyx_h9_20261102b and are not recomputed here.

- Criterion pass rate over 6 paired task and repetition cells: earned 0.625, free 0.521, no memory 0.438, raw traces 0.438.
- Of 11 distilled candidates, 1 passed solo replay and was admitted (L_T1.C8_79e93c16).
- The poison story: "the screen passed all 11 candidates, causal replay rejected the 3 planted source candidates."
- Caveat: no answer in any arm passed the full rubric.
- Gated write back goes only through `pyx.approval.propose()`, never a direct bank write. Only a human APPROVED or DENIED decision writes an approval row (HUMAN_APPROVED or HUMAN_DENIED), and that decision is bound to the exact text's sha256 (`TextMismatchError` otherwise).
- The bank's definition of earned is `pyx.arms.earned_ids`: a poison pass, a replay pass, and a HUMAN_APPROVED approval row.

## 3. Scope

1. Close the consumer read path so no unadmitted text crosses the MCP boundary (ticket 1).
2. A consumer agent that, given a task id, fetches earned lessons over MCP from a running `python -m pyx.mcp_server`, puts them in its context, answers, and records exactly which lesson ids and sha256 values it used.
3. Gated write back: a lesson the consumer proposes becomes a candidate that must pass the existing poison check and causal replay, then goes to `propose()` and waits for Ashutosh's decision.
4. Keyless tests for every step, using the existing recorded call log pattern (`pyx/recording.py`, `pyx/replay_client.py`).

## 4. Non goals

- No MCP write tool in this step unless open decision 5 says otherwise.
- No change to the frozen eval, runs/pyx_h9_20261102b, the tag hackathon-judged-f97708e, the banner, the demo portal or the dashboard.
- No change to README.md while PR 61 is open against it.
- No new definition of earned, no new reason codes, no change to the admission chain in EVAL.md.
- No live model calls or spend without Ashutosh's approval for that run, with its cap stated first.
- No relitigation of the settled numbers.

## 5. API surface (designed before implementation)

### 5.1 MCP read tools (existing server, ticket 1 changes only the second tool's output)

```
query_earned_lessons(task_id: str | None = None, criterion_id: str | None = None) -> list[LessonView]
get_lesson_provenance(lesson_id: str) -> ProvenanceRecord
```

`LessonView`: lesson_id, text, text_sha256, fixes_criterion_id, task_id, scope, status, version. Returned only for earned lessons.

`ProvenanceRecord`: the LessonView fields plus provenance, earned, decisions, replay_repetitions. Invariant after ticket 1: `text` is present if and only if `earned` is true. For any other candidate the record carries `text_sha256`, `earned: false`, and its verdict rows, never its text. An unknown id stays an error.

### 5.2 Consumer agent (ticket 3 onward; package location is open decision 2)

```
fetch_earned(server_url: str, task_id: str) -> list[LessonView]
build_context(lessons: Sequence[LessonView]) -> ConsumerContext
answer(task_id: str, context: ConsumerContext, client) -> ConsumerAnswer
```

`ConsumerContext` holds the lesson texts in the same layout the earned arm uses (spec Amendment 4) and the list of (lesson_id, text_sha256) it was built from. `fetch_earned` refuses any entry whose text does not hash to its `text_sha256`. `ConsumerAnswer` records the answer, the run id, and the used (lesson_id, text_sha256) pairs, so every use is traceable to the exact admitted text.

### 5.3 Gated write back (ticket 5)

```
stage_candidate(answer: ConsumerAnswer, text: str, fixes_criterion_id: str) -> Candidate
```

The staged candidate is written through the existing `CandidateStore` into the consumer's own run directory, never into a run the bank already serves. From there it takes the existing chain unchanged: `pyx.poison.check_candidate`, causal replay, then `pyx.approval.propose()`. `propose()` already refuses without a poison pass and a replay pass row (`NotAdmissibleError`). Only `pyx.approval.decide()` with Ashutosh's APPROVED or DENIED writes the approval row.

## 6. Tickets (session sized, one PR each, each finished and verified before the next)

1. Close the provenance leak. DONE in this PR. Failing test first (evals/test_pyx_mcp_read_path.py), then `LessonBank.provenance` drops `text` for any candidate that is not earned. Verified against runs/pyx_h9_20261102b: all 34 unadmitted candidate ids across the run's candidates files come back without text; the admitted lesson keeps its text.
2. Settle the open decisions below with Ashutosh and record each as an ADR. No code.
3. Consumer read client: `fetch_earned` and `build_context` against an in process `build_server(bank)`, with a test that a tampered text (hash mismatch) is refused and that a non earned id never enters a context.
4. Consumer answer step: `answer` with a recorded call log, keyless replay test, used lesson ids recorded in the output. Any live recording run needs Ashutosh's approval and a stated cap first.
5. Gated write back: `stage_candidate` plus a test that proves the staged lesson cannot reach the bank or the earned set without poison pass, replay pass and a human approval row bound to its sha256.
6. Proof that using a lesson worked, as decided in open decision 3, as a rerunnable script with its real output in the PR body.

## 7. Open decisions for Ashutosh (not resolved here)

1. Rejected text: hide the record entirely, or show only its hash and status. Ticket 1 ships the conservative default, hash and status with verdict rows and no text. Hiding entirely would also remove the verdict rows that explain why a lesson was rejected.
2. Package boundary: a separate consumer package, with a producer and consumer import ban enforced by a test or a lint rule, or the consumer living inside `pyx/`.
3. What proves that using a lesson worked. The current lean is a replay style before and after on a held out task. EVAL.md section 4 keeps held out tasks out of the counted run, so this would be a new measurement, not part of the counted result.
4. Sequencing. Hackathon Builder proposed landing these before the consumer: a positive control for the poison screen, one held out transfer task, a counted ledger in CI (dash check and README suite count), a chart generated from runs/pyx_h9_20261102b/RESULTS.md with a consistency test, and rerunnable live test scripts. The alternative is the consumer first, as this spec orders it, with those items after.
5. Write back surface: keep write back a local command (this spec's default), or add an MCP write tool that can only call `propose()`.
