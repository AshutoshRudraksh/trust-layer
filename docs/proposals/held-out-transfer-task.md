# Proposal: one held out transfer task for the replay measurement

Status: Approved by Muse Nov 13, 2026, under Ashutosh's delegated authority. No model run has happened yet.
Serves: [ADR 0004](../adr/0004-proof-by-held-out-replay.md) and ticket 4 in [the Step 1 spec](../specs/step1-consumer-agent.md).
Date: Nov 13, 2026.

EVAL.md and runs/pyx_h9_20261102b/ were read for context only. Nothing here changes them, and nothing here is part of the counted result.

## 1. The task

One held out paper from the frozen manifest (pyx/tasks/manifest.md), given to the worker in the same prompt layout as T1 and T2: name the architecture figure's components and report what the results tables show, with sources.

Recommended: **H2, SWE-agent (arXiv 2405.15793v3)**. The manifest lists one architecture figure (Figure 1) and three results tables (Tables 1, 2, 3), the smallest held out table set, which keeps the rubric short and the worker input close to the training tasks. H1, H3, or H4 work the same way if Muse prefers; the choice is open question 1.

## 2. Why it is held out from the counted run

1. EVAL.md section 4: "Held out tasks stay out of the counted run." The counted run's claims are scoped to T1 and T2.
2. The manifest: "Held out papers H1 to H4 and any rubrics for them are never shown to the worker or the distiller", and "Held out paper texts and rubrics are not stored in this repo."
3. So this is a new measurement with its own run id, its own records, and its own report. Its numbers are never added to, averaged with, or compared as if they were the counted run's 0.625, 0.5208, 0.4375, 0.4375.

Consequence for this proposal: the rubric below fixes the criterion types, sources, and pass rules, but not the expected values. The filled rubric is written outside this repo, frozen before the run, and only its sha256 is committed (section 5).

## 3. How a lesson would transfer

The bank holds one earned lesson, L_T1.C8_79e93c16 (RESULTS.md, "How the one lesson was earned"). Its text tells the worker to define what auxiliary diagnostic columns in a results table measure and to summarize the authors' textual explanation of causes, trends, and implications. It was earned on T1.C8, a judged criterion that asks the answer to explain a result using the paper's analysis text.

Transfer means: on a paper the lesson never saw, the answer does that same kind of work (explains a table result with the paper's own analysis, defines a non obvious column) when the lesson is in context, and does not when it is absent, while nothing else in the answer gets worse.

## 4. Before and after replay protocol

1. **Arms.** Before: no memory (empty context). After: earned lesson only, the exact approved text of L_T1.C8_79e93c16, verified by its sha256 79e93c169ff6d8ae142cab2a2f4c2c229e118714e07e9aefce182a415e5a928d. Same prompt layout, differing only in context content, as EVAL.md section 5 requires for its arms.
2. **Pairing.** Each repetition runs both arms back to back with the same seed and prompt, as in the causal replay rule (EVAL.md section 6, A1). The before answer is never taken from an earlier run.
3. **Repetitions.** 5 paired repetitions. The counted run used 3; 5 is proposed because the budget allows it (section 7) and because one held out task gives few criteria, so more repetitions are the only way to tighten the result.
4. **Grading.** The same two judge setup as the counted run: a judged criterion fails only when both judges agree it fails; inconclusive criteria leave the denominator (EVAL.md section 8, A3). Programmatic criteria use the existing checker.
5. **Records.** A new run directory, runs/pyx_transfer_h2_<date>/, with calls, answers, verdicts, spend, and a RESULTS.md. Keyless replay from the call log must reproduce the verdicts byte for byte, as the counted run does.
6. **Order.** Freeze the rubric and record its hash, approve the cap, run, then read results. No rubric change after the first model call.

## 5. Rubric (shape and pass rules; values filled outside the repo before freezing)

Eight criteria, mirroring T1.json and T2.json:

| ID | Type | Source | Pass rule |
| --- | --- | --- | --- |
| H2.C1 | programmatic, number | Table 1 | The answer states the headline resolve rate on the full SWE-bench split for the main configuration and for the strongest baseline in that table, within the table's printed precision, and the difference. |
| H2.C2 | programmatic, number | Table 1 | The answer states one cost or efficiency figure from the table for the main configuration. |
| H2.C3 | programmatic, number | Table 3 | The answer states the ablation result for one named interface component: with and without, both values. |
| H2.C4 | programmatic, number | Table 3 | The answer identifies the largest drop in the ablation table and its size. |
| H2.C5 | programmatic, number | Table 3 | The answer states one further value from Table 3 with its row and column. |
| H2.C6 | programmatic, components | Figure 1 | The answer names the 9 labels inside the figure's boxes. |
| H2.C7 | judged | Results analysis section | **Transfer criterion.** PASS if the answer explains why a reported result came out as it did, using the cause the authors give in their analysis text, not only restating the number. |
| H2.C8 | judged | Table with a non obvious column | **Transfer criterion.** PASS if the answer defines what a non obvious column measures, using the paper's own definition. |

Table numbers follow arXiv 2405.15793v3, where the ablation table is Table 3.

Freezing: the filled rubric (exact values, tolerances, component list, the specific result and column for C7 and C8) is authored and frozen by Muse outside this repo. Its sha256 is committed in [held-out-rubric.sha256](held-out-rubric.sha256). It is given to the grader and the checker only, never to the worker or the distiller, and is published into the run directory after the run.

## 6. Models (Meta models only)

| Role | Model | Endpoint | Source of the choice |
| --- | --- | --- | --- |
| Worker | muse-spark-1.3-contributor | Meta Model API | README.md model table, the counted run's worker |
| Judge A | muse-spark-1.3-contributor | Meta Model API | same |
| Judge B | muse-spark-open-1026 (Meta's open weight model) | Baseten | same; Baseten is the host, the model is Meta's |

No distiller call: this measurement uses the already earned lesson and distills nothing.

## 7. Cost estimate against a $25 hard cap

**Prices.** The repo's pricing table (agents/meta_client.py) lists muse-spark-1.3-contributor at $0.10 per million input tokens and $0.20 per million output tokens. I could not cite current public Meta API pricing in this pass: whether that table matches Meta's current price page is **unknown**, and Baseten's per token price for Judge B is also **unknown** here. So the estimate uses the per call costs actually recorded in runs/pyx_h9_20261102b/calls.jsonl, which reflect what was billed in the counted run.

**Recorded per call costs** (counted run, read from calls.jsonl):

| Call | Calls | Mean cost | Max cost | Mean tokens in / out |
| --- | --- | --- | --- | --- |
| Worker (Meta) | 82 | $0.00300 | $0.00423 | 19,979 / 5,019 |
| Judge A (Meta) | 94 | $0.00046 | $0.00071 | 3,757 / 410 |
| Judge B (Baseten) | 104 | $0.00947 | $0.01573 | 3,999 / 1,051 |

Check on the Meta price: 19,979 input tokens at $0.10 per million is $0.0020, plus 5,019 output tokens at $0.20 per million is $0.0010, total $0.0030, which matches the recorded worker mean. So the repo table agrees with what was billed.

**Per answer.** 1 worker call plus 2 judged criteria, each judged by A and B:

- Mean: 0.00300 + 2 × 0.00046 + 2 × 0.00947 = **$0.0229**
- Using each call type's maximum: 0.00423 + 2 × 0.00071 + 2 × 0.01573 = **$0.0371**

**Per run.** 2 arms × 5 repetitions = 10 answers:

- Mean: 10 × 0.0229 = **$0.23** (about $0.04 Meta, $0.19 Baseten)
- Max per call: 10 × 0.0371 = **$0.37**

**Margins.** Two unknowns can raise this. A held out paper longer than T1 or T2 raises worker input tokens: at 5 times the input, the worker cost becomes about 0.0020 × 5 + 0.0010 = $0.011 per call, and the run becomes about $0.31 mean. Judge retries on malformed replies (the counted run made 104 Judge B calls for 94 Judge A calls, about 11% extra) add about 11% to Judge B. With both, the run stays under $0.50.

**Cap.** Proposed caps for this run: abort when new Meta spend passes $3 or new Baseten spend passes $5, and a hard stop at $25 total. The estimate is about 1% of the $25 cap. Credits available per the build plan: Meta about $149.30, Baseten about $97.80. The run spends money and needs explicit approval before it starts.

## 8. What counts as "using a lesson worked"

Pre registered, decided before the run:

**Worked**, if all three hold:

1. At least one transfer criterion (H2.C7 or H2.C8) fails in the before arm and passes in the after arm in at least 4 of the 5 paired repetitions. An inconclusive repetition counts as not passing, as EVAL.md's 2 of 3 rule treats it.
2. No criterion passes in the before arm and fails in the after arm in any repetition (no breaks).
3. The transfer criterion's judge disagreement rate in the after arm is reported, and is below 0.5. Above that, the result is reported as not determined.

**Not shown**, otherwise. Specifically: fewer than 4 of 5 fixes; or any break; or both arms already pass the transfer criteria (nothing to fix); or too many inconclusive verdicts to apply rule 1. A "not shown" result is reported in full, not retried with a different rubric.

Either way the report states plainly: one task, one lesson, 5 repetitions, and that this says nothing about the counted run's numbers or about lessons in general.

## 9. Rulings (Muse, Nov 13, 2026)

1. Paper: H2, SWE-agent, arXiv 2405.15793v3.
2. Repetitions: 5 paired repetitions.
3. Caps: abort when new Meta spend passes $3 or new Baseten spend passes $5; hard stop at $25 total; all inside a $40 combined envelope for tonight. Enforced in code by pyx/transfer_run.py.
4. Judge B stays muse-spark-open-1026 on Baseten, the same host as the counted run.
5. Rubric: authored and frozen by Muse outside the repo, given to the grader and the checker only, never to the worker or the distiller, published into the run directory after the run. Frozen sha256: 2e7de886b5bfd18c42a4d8563c8d39ddd7c4944c63478a3e19c4e0dcbd75a143.
6. Freeze rulings: table numbering follows arXiv v3, so the ablation criteria H2.C3, H2.C4, and H2.C5 source Table 3; H2.C1 is scoped to the full SWE-bench split; H2.C6 counts the 9 labels inside the figure's boxes.

## 10. Questions as asked before the rulings

1. Which held out paper: H2 as recommended, or H1, H3, H4?
2. Who writes and freezes the filled rubric outside the repo, and where is it stored?
3. 5 repetitions, or 3 to match the counted run?
4. The caps in section 7: $3 Meta, $5 Baseten, $25 hard stop. Approve, or set others?
5. Is Judge B on Baseten acceptable under "Meta models only" (Meta's model on a third party host)?
