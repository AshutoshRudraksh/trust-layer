# ADR 0002: rejected lessons are served as hash and status, never text

Status: Decided Nov 12, 2026 by Muse under Ashutosh's delegated authority; Ashutosh may revisit.
Spec: open decision 1 in docs/specs/step1-consumer-agent.md.

## Decision

Keep what ticket 1 ships ([ADR 0001](0001-gated-consumer-read-path.md)). A candidate that is not earned is served with its `text_sha256`, `earned: false`, provenance, and verdict rows. Its text is never served. The record is not hidden entirely.

## Why

The verdict rows explain why a lesson was rejected. Hiding the record would remove that explanation without making anything safer, because the text is already gone.

## Consequences

No code change. The tests in evals/test_pyx_mcp_read_path.py stay the proof.
