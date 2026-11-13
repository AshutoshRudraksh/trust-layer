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

### 5.2 Consumer agent (ticket 8 onward; separate `pyx_consumer/` package, ADR 0003)

```
fetch_earned(server_url: str, task_id: str) -> list[LessonView]
build_context(lessons: Sequence[LessonView]) -> ConsumerContext
answer(task_id: str, context: ConsumerContext, client) -> ConsumerAnswer
```

`ConsumerContext` holds the lesson texts in the same layout the earned arm uses (spec Amendment 4) and the list of (lesson_id, text_sha256) it was built from. `fetch_earned` refuses any entry whose text does not hash to its `text_sha256`. `ConsumerAnswer` records the answer, the run id, and the used (lesson_id, text_sha256) pairs, so every use is traceable to the exact admitted text.

### 5.3 Gated write back (ticket 10; MCP write tool per ADR 0006)

```
stage_candidate(answer: ConsumerAnswer, text: str, fixes_criterion_id: str) -> Candidate
```

The staged candidate is written through the existing `CandidateStore` into the consumer's own run directory, never into a run the bank already serves. From there it takes the existing chain unchanged: `pyx.poison.check_candidate`, causal replay, then `pyx.approval.propose()`. `propose()` already refuses without a poison pass and a replay pass row (`NotAdmissibleError`). Only `pyx.approval.decide()` with Ashutosh's APPROVED or DENIED writes the approval row.

## 6. Tickets (session sized, one PR each, each finished and verified before the next)

Order per [ADR 0005](../adr/0005-hardening-before-consumer.md): hardening first, consumer after.

1. Close the provenance leak. DONE. Failing test first (evals/test_pyx_mcp_read_path.py), then `LessonBank.provenance` drops `text` for any candidate that is not earned. Verified against runs/pyx_h9_20261102b: all 34 unadmitted candidate ids across the run's candidates files come back without text; the admitted lesson keeps its text.
2. Settle the open decisions in section 7 and record each as an ADR. DONE: ADRs 0002 to 0006. No code.
3. Poison screen positive control: a test that the existing screen rejects a known poisoned lesson.
4. One held out transfer task, kept out of the counted run.
5. Counted ledger in CI: dash check and README suite count.
6. Chart generated from runs/pyx_h9_20261102b/RESULTS.md, with a consistency test.
7. Rerunnable live test scripts. Any run that calls a model needs Ashutosh's approval and a stated cap first.
8. Consumer read client in the separate `pyx_consumer/` package ([ADR 0003](../adr/0003-separate-consumer-package.md)), with the import ban test: `fetch_earned` and `build_context` against an in process `build_server(bank)`, with a test that a tampered text (hash mismatch) is refused and that a non earned id never enters a context.
9. Consumer answer step: `answer` with a recorded call log, keyless replay test, used lesson ids recorded in the output. Any live recording run needs Ashutosh's approval and a stated cap first.
10. Gated write back: `stage_candidate` and the MCP write tool that can only call `propose()` ([ADR 0006](../adr/0006-mcp-write-tool-calls-only-propose.md)), with a test that proves the staged lesson cannot reach the bank or the earned set without poison pass, replay pass and a human approval row bound to its sha256.
11. Proof that using a lesson worked: held out replay before and after, outside the counted run ([ADR 0004](../adr/0004-proof-by-held-out-replay.md)), as a rerunnable script with its real output in the PR body.

## 7. Decisions

All five were decided Nov 12, 2026 by Muse under Ashutosh's delegated authority; Ashutosh may revisit any of them.

1. Rejected text: hash and status, as ticket 1 ships. [ADR 0002](../adr/0002-rejected-text-hash-and-status.md).
2. Package boundary: a separate consumer package with a producer and consumer import ban enforced by a test. [ADR 0003](../adr/0003-separate-consumer-package.md).
3. Proof: replay before and after on a held out task, as a new measurement outside the counted run; EVAL.md untouched. [ADR 0004](../adr/0004-proof-by-held-out-replay.md).
4. Sequencing: hardening first, consumer after. [ADR 0005](../adr/0005-hardening-before-consumer.md).
5. Write back: an MCP write tool that can only call `propose()`. [ADR 0006](../adr/0006-mcp-write-tool-calls-only-propose.md).
