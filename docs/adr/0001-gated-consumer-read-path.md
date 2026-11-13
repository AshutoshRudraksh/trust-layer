# ADR 0001: the consumer read path serves text only for earned lessons

Status: accepted for the default; the alternative is open decision 1 in docs/specs/step1-consumer-agent.md.
Date: 2026-11-12

## Context

`get_lesson_provenance` in pyx/mcp_server.py returned `LessonBank.provenance`, which carried the full text of any candidate in the run, earned or not. A consumer agent reading the bank over MCP could therefore receive the text of lessons the admission chain rejected, including the planted source candidates. Before this change, calling the tool for L_T1.C1_9dd514bb on runs/pyx_h9_20261102b returned that planted candidate's text.

## Decision

`LessonBank.provenance` includes `text` only when the lesson is earned under `pyx.arms.earned_ids`. Every other candidate is served as its `text_sha256`, `earned: false`, provenance and verdict rows. The rule sits in the bank, the one place that already knows the earned set, so every caller of the view, MCP or otherwise, inherits it. `query_earned_lessons` already served earned lessons only and is unchanged.

## Consequences

- No unadmitted text crosses the MCP boundary. Tested in evals/test_pyx_mcp_read_path.py over every candidate id in runs/pyx_h9_20261102b and through the MCP tool for the 3 planted ids.
- An operator who needs a rejected lesson's text reads the run's candidates files directly; the served view no longer carries it.
- Open: whether rejected candidates should be hidden from the tool entirely instead (open decision 1).
