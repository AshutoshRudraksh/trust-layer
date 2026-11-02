"""PR A of the Pyx judges step: hidden rubric format and role gated loader.

Values asserted here are copied from the frozen drafts rubric_train1.md (T1 Reflexion
2303.11366v4) and rubric_train2.md (T2 Agentless 2407.01489v2), approved Nov 1, 2026.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyx.rubric import (
    RUBRIC_DIR,
    RubricAccessDeniedError,
    RubricValidationError,
    load_rubric,
    validate_rubric,
)


def _numbers(criterion):
    return [e["value"] for e in criterion["expected"]]


@pytest.mark.parametrize("task_id", ["T1", "T2"])
def test_rubric_loads_with_eight_criteria_seven_programmatic(task_id: str) -> None:
    rubric = load_rubric(task_id, role="judge")
    types = [c["type"] for c in rubric["criteria"]]
    assert len(types) == 8
    assert types.count("programmatic") == 7
    assert types.count("judged") == 1


def test_checker_role_is_allowed() -> None:
    assert load_rubric("T1", role="checker")["task_id"] == "T1"


@pytest.mark.parametrize("role", ["worker", "distiller", "", "admin"])
def test_worker_distiller_and_unknown_roles_are_blocked(role: str) -> None:
    with pytest.raises(RubricAccessDeniedError):
        load_rubric("T1", role=role)


def test_t1_values_match_frozen_markdown() -> None:
    r = load_rubric("T1", role="judge")
    assert r["paper"] == "2303.11366v4"
    c = {x["id"]: x for x in r["criteria"]}
    assert _numbers(c["T1.C1"]) == ["91.0", "80.1", "10.9"]
    assert _numbers(c["T1.C2"]) == ["7.5", "15.0"]
    assert _numbers(c["T1.C3"]) == ["0.60", "0.52", "0.68"]
    assert _numbers(c["T1.C4"]) == ["0.30", "0.55", "0.25"]
    assert _numbers(c["T1.C5"]) == ["0.77", "0.80"]
    assert c["T1.C6"]["components"] == ["Actor", "Evaluator", "Self-reflection"]
    assert c["T1.C6"]["count"] == 3
    assert c["T1.C7"]["components"] == ["short term memory", "long term memory"]
    assert c["T1.C8"]["type"] == "judged" and c["T1.C8"]["check"] == "judged"


def test_t2_values_match_frozen_markdown() -> None:
    r = load_rubric("T2", role="checker")
    assert r["paper"] == "2407.01489v2"
    c = {x["id"]: x for x in r["criteria"]}
    assert _numbers(c["T2.C1"]) == ["96", "300", "32.00"]
    assert _numbers(c["T2.C2"]) == ["0.70", "78166"]
    assert _numbers(c["T2.C3"]) == ["77", "81", "96", "15"]
    assert _numbers(c["T2.C4"]) == ["96", "88", "8"]
    assert _numbers(c["T2.C5"]) == ["81.67", "78.67", "3.00"]
    assert c["T2.C6"]["components"] == ["localization", "repair", "patch validation"]
    assert _numbers(c["T2.C7"]) == ["194", "38.80"]
    assert c["T2.C8"]["type"] == "judged"


@pytest.mark.parametrize("task_id", ["T1", "T2"])
def test_tolerance_is_half_unit_in_last_digit_and_counts_exact(task_id: str) -> None:
    for c in load_rubric(task_id, role="judge")["criteria"]:
        for e in c.get("expected", []):
            decimals = len(e["value"].split(".")[1]) if "." in e["value"] else 0
            assert e["kind"] == ("decimal" if decimals else "count")
            assert e["tolerance"] == (0.5 * 10 ** -decimals if decimals else 0)


def _good() -> dict:
    return json.loads((RUBRIC_DIR / "T1.json").read_text())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["criteria"].pop(),
        lambda r: r["criteria"][0].update(type="vibes"),
        lambda r: r["criteria"][0].update(check="judged"),
        lambda r: r["criteria"][0]["expected"][0].update(tolerance=1.0),
        lambda r: r["criteria"][1].update(id=r["criteria"][0]["id"]),
        lambda r: r["criteria"][0].pop("verdict"),
        lambda r: r["criteria"][7].update(type="programmatic"),
    ],
)
def test_malformed_rubric_is_rejected(mutate) -> None:
    r = _good()
    mutate(r)
    with pytest.raises(RubricValidationError):
        validate_rubric(r)


def test_unknown_task_is_rejected() -> None:
    with pytest.raises(FileNotFoundError):
        load_rubric("H1", role="judge")
