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

## Amendments, all trailing
All three columns are appended after run_id, in this order. Every specced column keeps its position, so a reader that takes the first ten columns still reads the spec schema.

- Amendment 1, column 11, `flags`: comma separated flags from grading, JUDGE_DISAGREE and JUDGE_UNAVAILABLE. Approved by Ashutosh in the PR D plan, so INCONCLUSIVE can be recorded without inventing a reason code: result inconclusive, empty reason_code, flag JUDGE_UNAVAILABLE.
- Amendment 2, column 12, `task_id`: the task a grade row is about, empty for lesson rows. Approved by Ashutosh in the PR D2 plan, because the specced row has no column that says which task a grade grades.
- Amendment 3, column 13, `copy`: the paper copy a row is about, `clean` or `planted`, after task_id. Empty when no paper copy applies, as for rows graded on hand written fixture answers. Approved by Ashutosh on Nov 2, 2026, because a T1 clean row and a T1 planted row with otherwise identical content were written as duplicates and one was dropped, so the poison arm could not be told apart from the clean run.

No reason code was added by any amendment.
