"""PR C2b tests: judge_criterion, the combining rule and grade_answer. Both clients are faked; no network."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import pytest

from agents.http_retry import RateLimitedError
from agents.meta_client import BudgetCapExceededError, EmptyReplyError
from agents.spend_ledger import SpendLedger
from pyx import judges
from pyx.checker import PASS, FAIL
from pyx.judges import (
    ERROR,
    INCONCLUSIVE,
    JUDGE_DISAGREE,
    JUDGE_UNAVAILABLE,
    MALFORMED,
    combine,
    grade_answer,
    judge_criterion,
)
from pyx.rubric import load_rubric

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pyx"


@dataclass
class _Reply:
    output_text: str
    input_tokens: int = 10
    output_tokens: int = 2
    cost_usd: float = 0.001
    model: str = "fake"


class FakeJudge:
    """Returns scripted replies or raises scripted errors, recording each prompt."""

    def __init__(self, script: List[object], ledger: SpendLedger | None = None) -> None:
        self.script = list(script)
        self.prompts: List[str] = []
        self.kwargs: List[dict] = []
        self.ledger = ledger

    def _next(self, prompt: str, kwargs: dict) -> _Reply:
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Reply(str(item))

    def respond(self, prompt: str, **kwargs) -> _Reply:
        return self._next(prompt, kwargs)

    def chat(self, prompt: str, **kwargs) -> _Reply:
        return self._next(prompt, kwargs)


def _criterion(task: str = "T1", cid: str = "T1.C8") -> dict:
    return next(c for c in load_rubric(task, role="judge")["criteria"] if c["id"] == cid)


# 4. Retry


def test_one_malformed_reply_is_retried() -> None:
    a, b = FakeJudge(["PASS, mostly", "PASS"]), FakeJudge(["PASS"])
    result = judge_criterion(_criterion(), "answer", a, b)
    assert result.judge_a.verdict == PASS and result.judge_a.retries == 1
    assert result.status == PASS and result.flags == ()


def test_two_malformed_replies_give_malformed_and_flag() -> None:
    a, b = FakeJudge(["maybe", "still maybe"]), FakeJudge(["FAIL"])
    result = judge_criterion(_criterion(), "answer", a, b)
    assert result.judge_a.verdict == MALFORMED
    assert result.status == INCONCLUSIVE
    assert JUDGE_UNAVAILABLE in result.flags
    assert len(a.prompts) == 2


# 5. Combining


@pytest.mark.parametrize(
    "va,vb,status,flags",
    [
        (FAIL, FAIL, FAIL, ()),
        (PASS, FAIL, PASS, (JUDGE_DISAGREE,)),
        (FAIL, PASS, PASS, (JUDGE_DISAGREE,)),
        (PASS, PASS, PASS, ()),
        (FAIL, MALFORMED, INCONCLUSIVE, (JUDGE_UNAVAILABLE,)),
        (ERROR, FAIL, INCONCLUSIVE, (JUDGE_UNAVAILABLE,)),
        (PASS, ERROR, INCONCLUSIVE, (JUDGE_UNAVAILABLE,)),
        (MALFORMED, PASS, INCONCLUSIVE, (JUDGE_UNAVAILABLE,)),
        (ERROR, MALFORMED, INCONCLUSIVE, (JUDGE_UNAVAILABLE,)),
    ],
)
def test_combine(va: str, vb: str, status: str, flags: tuple) -> None:
    assert combine(va, vb) == (status, flags)


# 6. Errors


@pytest.mark.parametrize("exc", [EmptyReplyError("empty"), RateLimitedError("429")])
def test_judge_errors_become_error_for_that_judge(exc: Exception) -> None:
    a, b = FakeJudge([exc]), FakeJudge(["FAIL"])
    result = judge_criterion(_criterion(), "answer", a, b)
    assert result.judge_a.verdict == ERROR
    assert type(exc).__name__ in result.judge_a.error
    assert result.status == INCONCLUSIVE and JUDGE_UNAVAILABLE in result.flags


def test_budget_stop_halts_the_run() -> None:
    a, b = FakeJudge([BudgetCapExceededError("stop")]), FakeJudge(["PASS"])
    with pytest.raises(BudgetCapExceededError):
        judge_criterion(_criterion(), "answer", a, b)
    assert b.prompts == []


def test_judge_settings_temperature_zero_low_effort_2048() -> None:
    a, b = FakeJudge(["PASS"]), FakeJudge(["PASS"])
    judge_criterion(_criterion(), "answer", a, b)
    assert a.kwargs[0]["temperature"] == 0
    assert a.kwargs[0]["reasoning_effort"] == "low"
    assert a.kwargs[0]["max_output_tokens"] == 2048
    assert b.kwargs[0]["temperature"] == 0 and b.kwargs[0]["max_tokens"] == 2048


# 7. grade_answer


def test_grade_answer_calls_judges_only_for_judged_criteria(tmp_path: Path, monkeypatch) -> None:
    roles: List[str] = []
    real_load = judges.load_rubric

    def spy(task_id: str, role: str):
        roles.append(role)
        return real_load(task_id, role=role)

    monkeypatch.setattr(judges, "load_rubric", spy)
    ledger = SpendLedger(tmp_path / "l.json")
    ledger.record("meta", "m1", 0.5)
    ledger.record("baseten", "b1", 1.5)
    a, b = FakeJudge(["PASS"], ledger), FakeJudge(["FAIL"], ledger)
    answer = (FIXTURES / "T1_good.md").read_text()
    report = grade_answer(answer, "T1", a, b)
    assert roles == ["judge"]
    assert len(a.prompts) == 1 and len(b.prompts) == 1
    judged = [v for v in report.verdicts if v.criterion_id == "T1.C8"][0]
    assert judged.status == PASS and JUDGE_DISAGREE in judged.flags
    assert all(v.status in (PASS, FAIL) for v in report.verdicts)
    assert report.agreement == (0, 1)
    assert report.ledgers["meta"]["total_usd"] == pytest.approx(0.5)
    assert report.ledgers["baseten"]["total_usd"] == pytest.approx(1.5)
    assert report.meta_cap_usd == 40.0 and report.baseten_guide_usd == 25.0
    assert report.baseten_pricing_assumed is True


def test_grade_answer_surfaces_inconclusive(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "l.json")
    a, b = FakeJudge(["FAIL"], ledger), FakeJudge(["huh", "still huh"], ledger)
    answer = (FIXTURES / "T2_bad.md").read_text()
    report = grade_answer(answer, "T2", a, b)
    judged = [v for v in report.verdicts if v.criterion_id == "T2.C8"][0]
    assert judged.status == INCONCLUSIVE and JUDGE_UNAVAILABLE in judged.flags
    assert report.inconclusive == ("T2.C8",)
