"""PR H3 tests: exact text approval through gate/approval_gate.py (plan H tests 12 to 15). Local SQLite only."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from gate.approval_gate import ApprovalGate, DenialLockError
from pyx.approval import NotAdmissibleError, TextMismatchError, approval_text, decide, propose
from pyx.arms import earned_ids
from pyx.decisions import DecisionRow
from pyx.lessons import CandidateStore

CANDS = CandidateStore(Path(__file__).resolve().parent / "fixtures" / "pyx" / "replay" /
                       "e4_distill_candidates.jsonl").read()
C = CANDS[0]
LID = C.lesson.lesson_id


def _rows(lid=LID, replay="pass"):
    return [DecisionRow(lid, "poison", "pass", "", "", "", "", "", "0", "r1", "", "", "clean"),
            DecisionRow(lid, "replay", replay, "" if replay == "pass" else "NO_FIX", "T1.C1" if replay == "pass"
                        else "", "", "", "", "0", "r1", "", "T1", "clean")]


def test_the_prompt_shows_exact_text_hash_and_replay_evidence() -> None:
    text = approval_text(C, _rows()[1])
    assert C.lesson.text in text and C.provenance.text_sha256 in text and "fixed T1.C1" in text


def test_approved_writes_human_approved_and_the_lesson_is_earned() -> None:
    gate = ApprovalGate()
    record = propose(gate, C, _rows(), "ins1")
    row = decide(gate, record, C, "APPROVED", "Ashutosh", "r1", 0)
    assert (row.step, row.result, row.reason_code, row.lesson_id) == ("approval", "pass", "HUMAN_APPROVED", LID)
    assert gate.get_approval(record.approval_id).decided_by == "Ashutosh"
    assert earned_ids(_rows() + [row]) == {LID}


def test_denied_writes_human_denied_and_stays_locked_under_the_same_instruction() -> None:
    gate = ApprovalGate()
    record = propose(gate, C, _rows(), "ins1")
    row = decide(gate, record, C, "DENIED", "Ashutosh", "r1", 0)
    assert (row.result, row.reason_code) == ("fail", "HUMAN_DENIED") and earned_ids(_rows() + [row]) == set()
    with pytest.raises(DenialLockError):
        propose(gate, C, _rows(), "ins1")


def test_a_decision_on_another_text_is_refused() -> None:
    gate = ApprovalGate()
    record = propose(gate, C, _rows(), "ins1")
    with pytest.raises(TextMismatchError):
        decide(gate, record, CANDS[1], "APPROVED", "Ashutosh", "r1", 0)


def test_only_lessons_with_poison_and_replay_passes_can_be_proposed() -> None:
    with pytest.raises(NotAdmissibleError):
        propose(ApprovalGate(), C, _rows(replay="fail"), "ins1")
    with pytest.raises(NotAdmissibleError):
        propose(ApprovalGate(), C, _rows()[1:], "ins1")


def test_only_approved_or_denied_is_accepted() -> None:
    gate = ApprovalGate()
    record = propose(gate, C, _rows(), "ins1")
    with pytest.raises(ValueError):
        decide(gate, record, C, "yes", "Ashutosh", "r1", 0)
