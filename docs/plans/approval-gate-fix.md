# Approval gate fix: PENDING-only decide() and execute_approved() denial lock

Baseline: `main` at `16a525f`, 338 tests passing. No new statuses: approvals stay the plain strings `PENDING`, `APPROVED`, and `DENIED`. There is no `EXPIRED` or `EXECUTED` status in the schema; after a successful execute the approval row stays `APPROVED` and `actions.executed` is set to 1.

## 1. Root cause (16a525f)

`gate/approval_gate.py` `decide()` (line 391) checks that the approval exists (lines 396-401) and that the decision is `APPROVED` or `DENIED` (lines 392-394), then updates status by `approval_id` alone:

```
UPDATE approvals
SET status = ?, decided_at = ?, decided_by = ?, denial_reason = ?
WHERE approval_id = ?
```

(lines 404-411). There is no `AND status = 'PENDING'` predicate and no `rowcount` check, so a second `decide()` can overwrite a `DENIED` row as `APPROVED` (or an `APPROVED` row as `DENIED`) and still return success.

A deny does write a `denial_locks` row keyed by idempotency key, with `denied_instruction_id` set to the approval's `instruction_id` (schema at lines 185-193, insert at lines 413-430). `propose()` already honors that lock: the same instruction is refused, a new instruction clears the lock (lines 267-292). `execute_approved()` (line 451) does not read `denial_locks` at all. It only inspects `approvals.status` (lines 463-474): `DENIED` raises `DenialLockError`, any status other than `APPROVED` raises `UnapprovedExecutionError`, and an `APPROVED` row proceeds to `executor_fn`. After a deny-then-overwrite, status is `APPROVED`, so execution runs even though the lock row is still present.

`api/main.py` exposes `decide()` at `POST /approvals/{approval_id}/decide` (lines 139-154) and maps `KeyError` to 404 and `ValueError` to 400. A refused re-decide needs a typed error mapped to HTTP 409.

The overwrite also reaches Pyx. `pyx/approval.py` `decide()` (lines 46-55) calls `gate.decide()` and then writes a `DecisionRow` from the decision argument, not from the stored gate status. `pyx/arms.py` `earned_ids()` (lines 53-57) admits a lesson that has poison pass, replay pass, and a `HUMAN_APPROVED` approval row. A flipped decide therefore produces a `HUMAN_APPROVED` row that `earned_ids()` will admit.

## 2. The two guards

1. `decide()` updates only with `WHERE approval_id = ? AND status = 'PENDING'`. If the `UPDATE` `rowcount` is 0, raise a typed `ApprovalNotPendingError` (do not return success). A missing approval stays a `KeyError`. Map `ApprovalNotPendingError` to HTTP 409 in `api/main.py`. Rollback any open transaction before raising, so a losing concurrent decide does not hold the SQLite lock.

2. `execute_approved()` refuses, with `DenialLockError`, when a `denial_locks` row for the approval's idempotency key has `denied_instruction_id` equal to the approval's `instruction_id`, even if `approvals.status` has been forced to `APPROVED`. A new approval from a different (new) `instruction_id` on the same idempotency key is allowed.

Keep the diff small. Do not invent statuses. Do not edit an existing test to make it pass.

## 3. Tests to write first (failing commit, then the matching guard)

Pending-guard tests, then the `decide()` fix, then execute-guard tests, then the `execute_approved()` fix:

1. Re-deciding `DENIED` to `APPROVED` is rejected and the row stays `DENIED`. Also re-deciding `APPROVED` to `DENIED`, and re-deciding an already executed approval (status still `APPROVED`, `actions.executed = 1`).
2. End-to-end: deny, re-decide `APPROVED`, then `execute_approved()`. `executor_fn` is never called and nothing is marked executed.
3. `decide()` raises when the `UPDATE` `rowcount` is 0 (no silent success). Two concurrent `decide()` calls on the same `PENDING` approval (separate connections against a file DB) result in exactly one winner and one raised error.
4. A Pyx lesson whose approval was flipped `DENIED` to `APPROVED` never shows up in `arms.earned_ids()`. The test goes through `pyx.approval.decide()`, which is the path that writes the `DecisionRow` `earned_ids()` reads.
5. `POST /approvals/{approval_id}/decide` returns 409 on a re-decide.
6. Defense in depth, after the pending guard: even if status is forced to `APPROVED` in the DB, `execute_approved()` refuses when the lock's `denied_instruction_id` equals the approval's `instruction_id`, and `executor_fn` is not called. A new approval from a different `instruction_id` on the same idempotency key is allowed to execute.

The 338 existing tests must still pass. A rider, in its own commit and not a gate behavior change: add `answers.jsonl` and `candidates_r2_planted.jsonl` to the list of files expected to differ on rerun in `runs/pyx_h9_20261102b/RESULTS.md`. Do not touch `README.md`.
