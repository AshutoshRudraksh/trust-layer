from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"

# Hidden rubrics are visible only to grading roles. The worker and the distiller must
# never see rubric text (Pyx spec v1.2, Section 5), so access is checked at this boundary.
ALLOWED_ROLES = frozenset({"judge", "checker"})

CRITERIA_PER_RUBRIC = 8
PROGRAMMATIC_PER_RUBRIC = 7
CHECKS_BY_TYPE = {
    "programmatic": frozenset({"number", "count", "components"}),
    "judged": frozenset({"judged"}),
}
REQUIRED_FIELDS = ("id", "type", "check", "source", "verdict", "expected")


class RubricAccessDeniedError(PermissionError):
    """Raised when a role other than judge or checker asks for hidden rubric text."""


class RubricValidationError(ValueError):
    """Raised when a rubric file does not match the frozen rubric format."""


def _half_unit_tolerance(value: str) -> float:
    decimals = len(value.split(".")[1]) if "." in value else 0
    return 0.5 * 10 ** -decimals if decimals else 0


def _validate_expected(criterion_id: str, entry: Dict[str, Any]) -> None:
    value = entry.get("value")
    if not isinstance(value, str):
        raise RubricValidationError(f"{criterion_id}: expected value must be a string, got {value!r}")
    try:
        float(value)
    except ValueError as exc:
        raise RubricValidationError(f"{criterion_id}: expected value {value!r} is not a number") from exc
    kind = "decimal" if "." in value else "count"
    if entry.get("kind") != kind:
        raise RubricValidationError(f"{criterion_id}: value {value} must have kind {kind}")
    if entry.get("tolerance") != _half_unit_tolerance(value):
        raise RubricValidationError(
            f"{criterion_id}: tolerance for {value} must be half a unit in the last digit "
            f"({_half_unit_tolerance(value)}), counts exact"
        )


def validate_rubric(rubric: Dict[str, Any]) -> Dict[str, Any]:
    criteria = rubric.get("criteria")
    if not rubric.get("task_id") or not rubric.get("paper") or not isinstance(criteria, list):
        raise RubricValidationError("rubric needs task_id, paper and a criteria list")
    if len(criteria) != CRITERIA_PER_RUBRIC:
        raise RubricValidationError(f"rubric needs {CRITERIA_PER_RUBRIC} criteria, got {len(criteria)}")

    seen_ids = set()
    for criterion in criteria:
        missing = [f for f in REQUIRED_FIELDS if f not in criterion]
        if missing:
            raise RubricValidationError(f"{criterion.get('id', '?')}: missing fields {missing}")
        criterion_id = criterion["id"]
        if criterion_id in seen_ids:
            raise RubricValidationError(f"duplicate criterion id {criterion_id}")
        seen_ids.add(criterion_id)
        allowed_checks = CHECKS_BY_TYPE.get(criterion["type"])
        if allowed_checks is None:
            raise RubricValidationError(f"{criterion_id}: unknown type {criterion['type']!r}")
        if criterion["check"] not in allowed_checks:
            raise RubricValidationError(
                f"{criterion_id}: check {criterion['check']!r} is not valid for type {criterion['type']!r}"
            )
        if criterion["check"] == "components" and len(criterion.get("components") or []) != criterion.get("count"):
            raise RubricValidationError(f"{criterion_id}: components list must match count")
        for entry in criterion["expected"]:
            _validate_expected(criterion_id, entry)

    programmatic = sum(1 for c in criteria if c["type"] == "programmatic")
    if programmatic != PROGRAMMATIC_PER_RUBRIC:
        raise RubricValidationError(
            f"rubric needs {PROGRAMMATIC_PER_RUBRIC} programmatic criteria, got {programmatic}"
        )
    return rubric


def load_rubric(task_id: str, role: str) -> Dict[str, Any]:
    """Return the validated hidden rubric for a task, only to the judge or checker role."""
    if role not in ALLOWED_ROLES:
        raise RubricAccessDeniedError(
            f"role {role!r} may not read hidden rubrics; only {sorted(ALLOWED_ROLES)} may"
        )
    path = RUBRIC_DIR / f"{task_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no committed rubric for task {task_id!r} at {path}")
    return validate_rubric(json.loads(path.read_text(encoding="utf-8")))
