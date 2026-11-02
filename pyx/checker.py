from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Programmatic criteria are checked by code only (Ashutosh's ruling 1); judged
# criteria are left for the two judges. Pure functions: no model calls, no network.
PASS = "PASS"
FAIL = "FAIL"
PENDING_JUDGE = "PENDING_JUDGE"

# A number token: optional minus (kept, ruling 3) unless it is a hyphen inside a
# word such as GPT-4, optional $, digits with thousands commas, optional decimals, optional %.
_DIGITS = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_NUMBER = re.compile(rf"(?<![\w.])(-?)\$?({_DIGITS})%?|(?<=[\w.])-?({_DIGITS})%?")
_PARAGRAPH = re.compile(r"\S(?:.*?)(?=\n\s*\n|\Z)", re.S)


@dataclass(frozen=True)
class Evidence:
    target: str
    found: bool
    matched_text: Optional[str] = None
    offset: Optional[int] = None


@dataclass(frozen=True)
class Verdict:
    criterion_id: str
    status: str
    check: str
    evidence: Tuple[Evidence, ...] = ()


def _numbers(text: str, base: int) -> List[Tuple[float, str, int]]:
    """Every number in text as (value, matched text, absolute offset)."""
    found = []
    for m in _NUMBER.finditer(text):
        if m.group(2) is not None:
            sign, digits, start = m.group(1), m.group(2), m.start(1)
        else:
            sign, digits, start = "", m.group(3), m.start(3)
        value = float(digits.replace(",", ""))
        found.append((-value if sign else value, text[start:m.end()], base + start))
    return found


def _match_numbers(expected: List[Dict[str, Any]], numbers) -> List[Evidence]:
    evidence = []
    for entry in expected:
        target = float(entry["value"])
        hit = next((n for n in numbers if abs(n[0] - target) <= entry["tolerance"] + 1e-9), None)
        evidence.append(
            Evidence(entry["value"], True, hit[1], hit[2]) if hit else Evidence(entry["value"], False)
        )
    return evidence


def _check_numbers(text: str, criterion: Dict[str, Any]) -> Tuple[str, Tuple[Evidence, ...]]:
    # All of a criterion's values must appear in one paragraph (ruling 1), so a value
    # quoted for a different claim elsewhere in the answer does not count.
    best: List[Evidence] = []
    for paragraph in _PARAGRAPH.finditer(text):
        evidence = _match_numbers(criterion["expected"], _numbers(paragraph.group(0), paragraph.start()))
        if all(e.found for e in evidence):
            return PASS, tuple(evidence)
        if sum(e.found for e in evidence) > sum(e.found for e in best):
            best = evidence
    return FAIL, tuple(best or _match_numbers(criterion["expected"], []))


def _check_components(text: str, criterion: Dict[str, Any]) -> Tuple[str, Tuple[Evidence, ...]]:
    evidence = []
    for name in criterion["components"]:
        words = re.split(r"[\s-]+", name.strip())
        m = re.search(r"\b" + r"[\s-]+".join(map(re.escape, words)) + r"\b", text, re.I)
        evidence.append(Evidence(name, True, m.group(0), m.start()) if m else Evidence(name, False))
    return (PASS if all(e.found for e in evidence) else FAIL), tuple(evidence)


def check_answer(answer_text: str, rubric: Dict[str, Any]) -> List[Verdict]:
    """One verdict per rubric criterion, in rubric order. Load the rubric with role checker."""
    verdicts = []
    for criterion in rubric["criteria"]:
        check = criterion["check"]
        if criterion["type"] == "judged":
            verdicts.append(Verdict(criterion["id"], PENDING_JUDGE, check))
            continue
        if check == "components":
            status, evidence = _check_components(answer_text, criterion)
        else:
            status, evidence = _check_numbers(answer_text, criterion)
        verdicts.append(Verdict(criterion["id"], status, check, evidence))
    return verdicts
