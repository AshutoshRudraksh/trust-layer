"""PR B of the Pyx judges step: the programmatic checker.

Fixtures in evals/fixtures/pyx are handwritten answers built only from the frozen
T1 and T2 rubric values. Each bad fixture breaks the criteria listed in BROKEN and
leaves every other programmatic criterion correct.
"""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

from pyx.checker import FAIL, PASS, PENDING_JUDGE, check_answer
from pyx.rubric import load_rubric

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pyx"
BROKEN = {"T1": {"T1.C1", "T1.C3", "T1.C6"}, "T2": {"T2.C2", "T2.C3", "T2.C6"}}
JUDGED = {"T1": "T1.C8", "T2": "T2.C8"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the checker must not open network connections")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _statuses(task_id: str, kind: str) -> dict:
    text = (FIXTURES / f"{task_id}_{kind}.md").read_text(encoding="utf-8")
    verdicts = check_answer(text, load_rubric(task_id, role="checker"))
    return {v.criterion_id: v.status for v in verdicts}


@pytest.mark.parametrize("task_id", ["T1", "T2"])
def test_good_answer_passes_all_programmatic_criteria(task_id: str) -> None:
    statuses = _statuses(task_id, "good")
    assert len(statuses) == 8
    assert statuses.pop(JUDGED[task_id]) == PENDING_JUDGE
    assert set(statuses.values()) == {PASS}


@pytest.mark.parametrize("task_id", ["T1", "T2"])
def test_bad_answer_fails_exactly_the_broken_criteria(task_id: str) -> None:
    statuses = _statuses(task_id, "bad")
    assert statuses.pop(JUDGED[task_id]) == PENDING_JUDGE
    failed = {cid for cid, status in statuses.items() if status == FAIL}
    assert failed == BROKEN[task_id]


def _rubric_with(check: str, values=(), components=()) -> dict:
    expected = []
    for value in values:
        decimals = len(value.split(".")[1]) if "." in value else 0
        expected.append(
            {"value": value, "kind": "decimal" if decimals else "count",
             "tolerance": 0.5 * 10 ** -decimals if decimals else 0}
        )
    criterion = {"id": "X.C1", "type": "programmatic", "check": check, "expected": expected}
    if components:
        criterion.update(components=list(components), count=len(components))
    return {"task_id": "X", "criteria": [criterion]}


@pytest.mark.parametrize(
    "text, values, status",
    [
        ("a gain of 10.90 points", ["10.9"], PASS),
        ("78,166 tokens", ["78166"], PASS),
        ("cost $0.70 each", ["0.70"], PASS),
        ("rate 32.00%", ["32.00"], PASS),
        ("a gain of 10.96 points", ["10.9"], FAIL),
        ("a gain of 10.94 points", ["10.9"], PASS),
        ("15 issues", ["16"], FAIL),
        ("delta -0.25", ["0.25"], FAIL),
        ("GPT-4 scored 80.1", ["4", "80.1"], PASS),
        ("three phases", ["3"], FAIL),
        ("96 of 300\n\nlater 32.00", ["96", "300", "32.00"], FAIL),
    ],
)
def test_number_normalization_tolerance_and_paragraph_window(text, values, status) -> None:
    [verdict] = check_answer(text, _rubric_with("number", values=values))
    assert verdict.status == status


def test_components_match_case_and_hyphen_insensitively_with_offsets() -> None:
    text = "It uses an actor, an EVALUATOR and self reflection plus short-term memory."
    rubric = _rubric_with("components", components=["Actor", "Evaluator", "Self-reflection", "short term memory"])
    [verdict] = check_answer(text, rubric)
    assert verdict.status == PASS
    evidence = {e.target: e for e in verdict.evidence}
    assert evidence["Self-reflection"].matched_text == "self reflection"
    assert text[evidence["Evaluator"].offset:].startswith("EVALUATOR")


def test_number_evidence_reports_matched_text_offset_and_missing_values() -> None:
    text = "Gain of 10.90 over 80.1."
    [verdict] = check_answer(text, _rubric_with("number", values=["10.9", "80.1", "91.0"]))
    assert verdict.status == FAIL
    evidence = {e.target: e for e in verdict.evidence}
    assert evidence["10.9"].matched_text == "10.90" and evidence["10.9"].offset == 8
    assert evidence["91.0"].found is False and evidence["91.0"].offset is None


def test_list_comma_is_not_part_of_a_number() -> None:
    [verdict] = check_answer("gives 77, then 81", _rubric_with("number", values=["77", "81"]))
    assert [e.matched_text for e in verdict.evidence] == ["77", "81"]
