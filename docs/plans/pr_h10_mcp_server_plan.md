Pyx H10: the read only MCP server for earned lessons (spec Amendment 1)

## Context

Spec Amendment 1, locked Nov 1, 2026: Horizon 0 includes a read only remote
MCP server over the bank of earned lessons. Two tools: query earned lessons
by task family or criterion, and fetch a lesson's provenance and verdict
record. HTTP transport. No write tools. The server is also the project's
rollout surface: any MCP client can inspect what the bank holds and why
each lesson was admitted, without keys and without touching the pipeline.

## Design

1. pyx/bank.py, pure logic, no new protocol code. A LessonBank loads one
   run directory: every candidates*.jsonl file in it through the existing
   CandidateStore, decisions.tsv through the existing read_decisions, and
   replay_reps.tsv when present. A directory without decisions.tsv, or
   without any candidates file, is refused with a clear error. The earned
   set is computed by pyx.arms.earned_ids, the pipeline's own function, so
   the server can never drift from the pipeline's definition of earned:
   a poison pass, a replay pass, and an approval row with HUMAN_APPROVED.
2. Two query functions on the bank: earned_lessons(task_id=None,
   criterion_id=None) returning the earned lessons matching the filters
   (task family is the task part of the lesson's target criterion), and
   provenance(lesson_id) returning the lesson, its provenance, every
   decisions row recorded for it, and its per repetition replay rows when
   the run recorded them. An unknown lesson id is an error, not an empty
   result.
3. pyx/mcp_server.py, the wiring. A FastMCP server from the official mcp
   Python SDK, streamable HTTP transport, registering exactly the two
   tools over the bank functions and nothing else. Entry point:
   python -m pyx.mcp_server --run-dir DIR [--host H] [--port N], host
   defaulting to 127.0.0.1 and port to 8377. The SDK is an optional
   dependency (a new mcp extra in pyproject.toml) imported lazily, so the
   core pipeline and its tests never require it.
4. Results are JSON objects built from the committed records verbatim:
   lesson id, text, text sha256, target criterion, scope, and for
   provenance the distiller, source paper and kind, replay run ids,
   approver and approval time, plus the recorded verdict rows. Nothing is
   summarized, scored, or reworded by the server.

## Tests

evals/test_pyx_bank.py, no SDK needed except where marked:

1. A synthetic run directory: two candidates, decisions rows earning one
   (poison pass, replay pass, approval HUMAN_APPROVED) and failing the
   other at replay (REGRESSION). Query returns only the earned lesson;
   the task and criterion filters include and exclude correctly;
   provenance returns the earned lesson's rows, and the failed lesson's
   provenance is still fetchable (the record is evidence, earned or not).
2. Refusals: a directory without decisions.tsv is refused; a directory
   without any candidates file is refused; an unknown lesson id errors.
3. The committed pilot record loads: its earned set is empty (every pilot
   candidate failed replay), a query returns an empty list, and
   provenance for a pilot lesson returns its recorded rows.
4. With the mcp extra installed (importorskip): the server registers
   exactly two tools, named query_earned_lessons and
   get_lesson_provenance, and no others.

Live test for the PR: in a fresh clone with the mcp extra installed,
boot the server on the committed pilot record, connect with the SDK
client over HTTP, list the tools, call query_earned_lessons (empty, as
the pilot earned nothing), and call get_lesson_provenance for a pilot
lesson. Then the same boot against a synthetic earned bank built by the
test fixture, showing a nonempty query. Outputs are pasted into the PR
body verbatim.

## Departures

None planned. If one appears, it is reported in one line as it happens
and named in the PR body.
