# decisions.tsv columns

decisions.tsv is the public log of every grade and verdict (spec Section 9). It is tab separated with one header line. Code: `pyx/decisions.py`.

## Specced columns (spec Section 4), in this order
1. lesson_id
2. step: poison, replay or approval; `grade` for grade rows (approved for PR D2)
3. result: pass or fail; `inconclusive` for a grade where a judge gave no real verdict (approved for PR D)
4. reason_code: empty or one of the frozen six: UNTRUSTED_SOURCE, NO_FIX, REGRESSION, JUDGE_DISAGREE, HUMAN_DENIED, HUMAN_APPROVED
5. criteria_fixed
6. criteria_broken
7. judge_a
8. judge_b
9. seed
10. run_id

## Amendments, both trailing
Both columns are appended after run_id. Every specced column keeps its position, so a reader that takes the first ten columns still reads the spec schema.

- Amendment 1, column 11, `flags`: comma separated flags from grading, JUDGE_DISAGREE and JUDGE_UNAVAILABLE. Approved by Ashutosh in the PR D plan, so INCONCLUSIVE can be recorded without inventing a reason code: result inconclusive, empty reason_code, flag JUDGE_UNAVAILABLE.
- Amendment 2, column 12, `task_id`: the task a grade row is about, empty for lesson rows. Approved by Ashutosh in the PR D2 plan, because the specced row has no column that says which task a grade grades.

No reason code was added by either amendment.
