# PILOT: thin_20261102_r1 (not a counted run)

Status: PILOT. Ashutosh ruled on Nov 2, 2026 that this run stands as a pilot only. It does not count toward any EVAL.md result.

Why it is not counted:
- It ran through an uncommitted driver (now committed here as scripts/pilot/thin_run.py for the record), not a committed and gated CLI.
- It shrank the protocol: one repetition instead of three, and cycle 1 (all four arms) did not run.
- Causal replay compared each lesson run against the single cycle 0 answer, not against a paired run without the lesson in the same repetition (see the replay review).

What ran (Nov 2, 2026, about 8:10 to 8:28 PM CT, main b49a0ff, EVAL.md sha256 2c0d2d3f37949ceb976f2c29c393f6ed4eaee98f09b7ab90c47b6842a8ba1b59):
- Cycle 0, one repetition: no memory on T1 clean and T2 clean, plus the poison condition (T1 planted).
- Distill, poison check, causal replay. Stopped before approval; no decision was typed.

Result: 10 candidates, 10 poison passes, 10 replay fails (9 REGRESSION, 9 of them breaking T2.C7; 1 NO_FIX). Nothing admissible for approval, nothing earned.

Spend: Meta $0.08143130 new (ledger $0.02754570 to $0.10897700). Baseten $0.23296250 new (ledger $0.12110175 to $0.35406425).

Keyless rerun: `python3 scripts/pilot/thin_run_keyless.py . runs/pilot_thin_20261102_r1 OUTDIR thin_20261102_r1` with keys unset and socket connect blocked reproduces decisions.tsv, replay_grades.tsv, answers.jsonl and both candidate stores byte for byte, with zero unused log lines. decisions.tsv sha256 3fdf3959e5472094cc787df9e58352ea378f8d88659703ffe77943f65ac3bba9.

Recorded model text and paper text inside calls.jsonl and answers.jsonl contain em and en dashes. They are verbatim records and are left unchanged, since editing them would break the keyless rerun.
