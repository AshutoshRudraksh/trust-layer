"""PR H1 tests: the four memory arm context builders and the poison step's copy (plan H tests 1 to 6)."""
from __future__ import annotations

import re
from pathlib import Path

from pyx.arms import ARMS, earned_ids, earned_lessons, free_lessons, no_memory, raw_traces
from pyx.decisions import DecisionLog, DecisionRow
from pyx.judges import grade_answer
from pyx.lessons import CandidateStore
from pyx.poison_run import run_poison
from pyx.rubric import load_rubric

ROOT = Path(__file__).resolve().parent
CANDS = CandidateStore(ROOT / "fixtures" / "pyx" / "replay" / "e4_distill_candidates.jsonl").read()
T1_BAD = (ROOT / "fixtures" / "pyx" / "T1_bad.md").read_text()


class _Judge:
    def __init__(self, reply):
        self.reply = reply

    def respond(self, prompt, **kw):
        return type("R", (), {"output_text": self.reply, "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0})()

    chat = respond


def _row(lid, step, result, reason=""):
    return DecisionRow(lid, step, result, reason, "", "", "", "", "0", "r1", "", "", "")


def test_arm_names_and_no_memory_is_empty() -> None:
    assert ARMS == ("no_memory", "raw_traces", "free_lessons", "earned_lessons")
    ctx = no_memory()
    assert (ctx.arm, ctx.text, ctx.lesson_ids) == ("no_memory", "", ())


def test_raw_traces_holds_the_answer_and_failure_view_but_no_rubric_text() -> None:
    report = grade_answer(T1_BAD, "T1", _Judge("FAIL"), _Judge("FAIL"))
    ctx = raw_traces([("T1", T1_BAD, report)])
    assert T1_BAD in ctx.text and "T1.C1" in ctx.text and "Table 1" in ctx.text and ctx.lesson_ids == ()
    outside = ctx.text.replace(T1_BAD, "")
    for c in load_rubric("T1", role="checker")["criteria"]:
        for s in [c["verdict"]] + [e["value"] for e in c["expected"]]:
            assert not re.search(rf"(?<![\w.]){re.escape(s)}(?![\w.])", outside), s


def test_free_lessons_carries_every_candidate_verbatim_in_order() -> None:
    ctx = free_lessons(CANDS)
    assert ctx.lesson_ids == tuple(c.lesson.lesson_id for c in CANDS)
    assert all(c.lesson.text in ctx.text for c in CANDS)


def test_earned_needs_poison_replay_and_human_approval_rows() -> None:
    a, b, c = (x.lesson.lesson_id for x in CANDS[:3])
    rows = [_row(a, "poison", "pass"), _row(a, "replay", "pass"), _row(a, "approval", "pass", "HUMAN_APPROVED"),
            _row(b, "poison", "pass"), _row(b, "replay", "pass"),
            _row(c, "poison", "pass"), _row(c, "replay", "pass"), _row(c, "approval", "fail", "HUMAN_DENIED")]
    assert earned_ids(rows) == {a}
    ctx = earned_lessons(CANDS, rows)
    assert ctx.lesson_ids == (a,) and CANDS[0].lesson.text in ctx.text and CANDS[1].lesson.text not in ctx.text


def test_all_arms_share_one_layout() -> None:
    assert free_lessons([]).text == earned_lessons(CANDS, []).text == raw_traces([]).text == no_memory().text == ""
    one = free_lessons(CANDS[:1]).text
    assert one == f"Lesson {CANDS[0].lesson.lesson_id}: {CANDS[0].lesson.text}"


def test_poison_rows_carry_the_copy_checked_against(tmp_path) -> None:
    store = CandidateStore(tmp_path / "c.jsonl")
    for c in CANDS[:4]:
        store.append(c)
    for copy in ("clean", "planted"):
        log = DecisionLog(tmp_path / f"{copy}.tsv")
        run_poison(store, "r1", 0, copy, log)
        assert {r.copy for r in log.read()} == {copy}
