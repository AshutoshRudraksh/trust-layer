# ADR 0006: write back is an MCP write tool that can only call propose()

Status: Decided Nov 12, 2026 by Muse under Ashutosh's delegated authority; Ashutosh may revisit.
Spec: open decision 5 in docs/specs/step1-consumer-agent.md.

## Decision

Add one MCP write tool. Its only effect is a call to `pyx.approval.propose()` for a candidate that was staged through `stage_candidate`. It cannot call `decide()`, cannot write the approval row, cannot write the bank or the earned set, and cannot skip the poison screen or causal replay, because `propose()` already refuses without a poison pass and a replay pass row (`NotAdmissibleError`).

## Why

An MCP tool lets an outside agent offer a lesson without shell access, while the human approval through `decide()` stays the only path to admission.

## Consequences

Ticket 10 adds the tool with tests that it reaches `propose()` only, that a call without a poison pass and replay pass is refused, and that no approval row is written by it.
