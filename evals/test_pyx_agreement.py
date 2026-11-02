"""PR D1a tests: two identical judge faults never count as agreement."""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from pyx.checker import FAIL, PASS
from pyx.judges import ERROR, MALFORMED, grade_answer, judges_agree, self_agreement

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pyx"


@pytest.mark.parametrize(
    "a,b,want",
    [
        (PASS, PASS, True),
        (FAIL, FAIL, True),
        (PASS, FAIL, False),
        (ERROR, ERROR, False),
        (MALFORMED, MALFORMED, False),
        (ERROR, MALFORMED, False),
        (PASS, ERROR, False),
    ],
)
def test_judges_agree_only_on_matching_real_verdicts(a: str, b: str, want: bool) -> None:
    assert judges_agree(a, b) is want


def test_self_agreement_counts_only_pairs_of_real_verdicts() -> None:
    first = [PASS, FAIL, ERROR, MALFORMED, PASS]
    second = [PASS, FAIL, ERROR, MALFORMED, FAIL]
    # agreeing pairs: 2 (PASS, FAIL); pairs with two real verdicts: 3; broken pairs: 2
    assert self_agreement(first, second) == (2, 3, 2)


def test_self_agreement_needs_equal_lengths() -> None:
    with pytest.raises(ValueError):
        self_agreement([PASS], [PASS, FAIL])


class _Reply:
    def __init__(self, text: str) -> None:
        self.output_text, self.input_tokens, self.output_tokens, self.cost_usd = text, 1, 1, 0.0


class _Broken:
    """A judge whose every reply is malformed."""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def respond(self, prompt: str, **kw) -> _Reply:
        self.calls.append(prompt)
        return _Reply("maybe")

    chat = respond


def test_grade_report_does_not_count_two_broken_judges_as_agreement() -> None:
    answer = (FIXTURES / "T1_good.md").read_text()
    report = grade_answer(answer, "T1", _Broken(), _Broken())
    assert report.agreement == (0, 0)
    assert report.judge_unavailable == 1
