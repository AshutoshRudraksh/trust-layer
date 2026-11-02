"""PR E2 tests: the failure view handed to the distiller, the distill prompt and the reply parser."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import pyx.failure_view as fv
from pyx.checker import FAIL, PASS
from pyx.distill import build_distill_prompt, parse_lesson
from pyx.failure_view import FailedCriterion, HeldOutTaskError, failure_view
from pyx.grade_run import grade_keyless
from pyx.judges import INCONCLUSIVE, JUDGE_DISAGREE, JUDGE_UNAVAILABLE
from pyx.lessons import TEXT_CAP
from pyx.rubric import load_rubric

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"
NAMES = ("T1_good", "T1_bad", "T2_good", "T2_bad")
ANSWERS = [(n[:2], (FIX / f"{n}.md").read_text()) for n in NAMES]
REPORTS = dict(zip(NAMES, grade_keyless(ANSWERS, FIX / "replay" / "d3_proof.jsonl")))


def test_t1_bad_view_lists_exactly_its_failed_criteria() -> None:
    view = failure_view(REPORTS["T1_bad"])
    assert [f.criterion_id for f in view] == ["T1.C1", "T1.C3", "T1.C6", "T1.C8"]
    assert view[0] == FailedCriterion("T1", "T1.C1", "programmatic", "Table 1", "2303.11366v4")
    assert view[3].type == "judged"


def test_good_answers_give_no_failures_and_all_four_answers_give_eight() -> None:
    assert failure_view(REPORTS["T1_good"]) == failure_view(REPORTS["T2_good"]) == []
    assert sum(len(failure_view(r)) for r in REPORTS.values()) == 8


def test_split_pass_and_inconclusive_are_not_failures() -> None:
    report = REPORTS["T1_bad"]
    c8 = report.verdicts[-1]
    for status, flags in ((PASS, (JUDGE_DISAGREE,)), (INCONCLUSIVE, (JUDGE_UNAVAILABLE,))):
        changed = replace(report, verdicts=report.verdicts[:-1] + (replace(c8, status=status, flags=flags),))
        assert "T1.C8" not in [f.criterion_id for f in failure_view(changed)]
    assert c8.status == FAIL


def test_held_out_task_raises_before_any_view(monkeypatch) -> None:
    real = fv.load_rubric
    monkeypatch.setattr(fv, "load_rubric", lambda t, role: dict(real(t, role=role), split="held_out"))
    with pytest.raises(HeldOutTaskError):
        failure_view(REPORTS["T1_bad"])


@pytest.mark.parametrize("task", ["T1", "T2"])
def test_prompt_carries_no_rubric_text_or_expected_values(task: str) -> None:
    name = f"{task}_bad"
    answer = dict(zip(NAMES, [a for _, a in ANSWERS]))[name]
    prompts = [build_distill_prompt(f, answer) for f in failure_view(REPORTS[name])]
    rubric = load_rubric(task, role="checker")
    secrets = [c["verdict"] for c in rubric["criteria"]]
    secrets += [c["expected_text"] for c in rubric["criteria"] if c.get("expected_text") not in (None, "", "judged")]
    secrets += [e["value"] for c in rubric["criteria"] for e in c.get("expected") or [] if isinstance(e, dict)]
    for prompt in prompts:
        assert answer in prompt and "BEGIN UNTRUSTED ANSWER" in prompt
        outside_answer = prompt.replace(answer, "")  # the answer may itself quote numbers; only our text counts
        for s in secrets:
            assert str(s) not in outside_answer


def test_parser_takes_the_lesson_line() -> None:
    assert parse_lesson("LESSON: Quote each number with its table.") == "Quote each number with its table."
    assert parse_lesson("  lesson:  Name every component.\n") == "Name every component."


@pytest.mark.parametrize("reply", ["", "PASS", "LESSON:", "LESSON: " + "x" * (TEXT_CAP + 1),
                                   "Here you go\nLESSON: two lines"])
def test_parser_refuses_malformed_replies(reply: str) -> None:
    assert parse_lesson(reply) is None
