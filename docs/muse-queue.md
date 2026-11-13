# Muse queue

Ordered work items awaiting Muse. Created Nov 13, 2026; no earlier queue doc existed in this repo, so later
items (lesson 2, U1) are listed by name only and keep whatever detail Muse already holds for them.

## 1. H2.C6 break diagnosis (ahead of lesson 2)

Source: runs/pyx_transfer_h2_20261113c (H2, 5 paired repetitions, earned lesson L_T1.C8_79e93c16). The lesson
fixed H2.C7 and H2.C8 in 5 of 5 pairs, but rep 4 broke H2.C6 (PASS without the lesson, FAIL with it), so under
the pre-registered bar (proposal section 8, rule 2) the result is "not shown". Diagnosed from local files only, at
no cost and with no model call. The answer text and the rubric values are not reproduced here.

**Which pair broke.** Rep 4 only. In reps 0 to 3 both arms pass H2.C6, and rep 4's no memory answer passes it.

**What the lesson arm's answer lost.** H2.C6 is a programmatic check that each of the 9 box labels of Figure 1
appears in the answer as written. The rep 4 lesson answer kept 4 of the 9 labels and dropped 5; all 5 are the
labels of the interface layer between the agent and the computer. It did not drop the content: it still
describes that layer, its parts and its commands, but organizes them under the paper's prose subsection names
from the method section instead of the figure's box labels. The no memory answer in the same pair uses the
figure's labels and keeps all 9. So the loss is **vocabulary, not coverage**: the figure's exact labels were
replaced by paraphrased section names. The rep 4 lesson answer is also the most results heavy of the ten
(its Results section is about 1.6 times its no memory partner's; Architecture is about the same length), which
fits the lesson pulling effort toward results analysis.

**What it feeds.** A lesson format fix: a lesson that adds work in one section should say to keep the other
section's required form (here, name components with the figure's own labels). Whether the H2.C6 check should
also accept close paraphrases is a separate rubric question and does not reopen this run.

**Retry rule.** Any future transfer retry is a new pre-registration on H1, H3 or H4, never H2.

## 2. Lesson 2

## 3. U1
