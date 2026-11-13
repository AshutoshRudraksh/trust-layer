# ADR 0004: proof that using a lesson worked is a held out replay, outside the counted run

Status: Decided Nov 12, 2026 by Muse under Ashutosh's delegated authority; Ashutosh may revisit.
Spec: open decision 3 in docs/specs/step1-consumer-agent.md.

## Decision

The proof is a replay style before and after on a held out task: the same task answered without and with the earned lesson, graded by the same rubric. It is a new measurement, reported separately, and is never added to the counted result.

## Constraints

1. EVAL.md is not edited. Its section 4 keeps held out tasks out of the counted run, and this measurement respects that.
2. runs/pyx_h9_20261102b/ and its counted results are not touched.
3. Any run that calls a model needs Ashutosh's approval and a stated cap first.

## Consequences

The held out transfer task (ticket 4) is a prerequisite. The proof itself is ticket 11.
