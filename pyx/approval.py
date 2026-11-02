"""Human exact text approval of lessons (spec Section 5) through gate/approval_gate.py.

Only a lesson with a poison pass and a replay pass row may be proposed. The
proposal carries the exact text and its sha256 in the payload, so the gate's
idempotency key and denial lock are bound to that text. Ashutosh's decision,
APPROVED or DENIED and nothing else, writes one approval row: pass with
HUMAN_APPROVED or fail with HUMAN_DENIED. A decision applied to a candidate whose
text hash is not the proposed one is refused. The bot never decides.
"""
from __future__ import annotations

from typing import Iterable

from gate.approval_gate import ActionProposal, ApprovalDecision, ApprovalGate, ApprovalRecord
from pyx.decisions import DecisionRow
from pyx.lessons import Candidate

OWNER, ACTION = "Ashutosh", "approve_lesson"


class NotAdmissibleError(ValueError):
    """The lesson lacks a poison pass or a replay pass row."""


class TextMismatchError(ValueError):
    """The decision is applied to a text other than the one proposed."""


def approval_text(cand: Candidate, replay_row: DecisionRow) -> str:
    return (f"Lesson {cand.lesson.lesson_id}\nsha256 {cand.provenance.text_sha256}\n"
            f"Replay: fixed {replay_row.criteria_fixed or 'none'}, broke {replay_row.criteria_broken or 'none'} "
            f"(run {replay_row.run_id})\nExact text:\n{cand.lesson.text}")


def propose(gate: ApprovalGate, cand: Candidate, rows: Iterable[DecisionRow], instruction_id: str) -> ApprovalRecord:
    lid = cand.lesson.lesson_id
    passed = {r.step: r for r in rows if r.lesson_id == lid and r.result == "pass"}
    if "poison" not in passed or "replay" not in passed:
        raise NotAdmissibleError(f"{lid} needs a poison pass and a replay pass before approval")
    payload = {"lesson_id": lid, "text": cand.lesson.text, "text_sha256": cand.provenance.text_sha256}
    return gate.propose(ActionProposal(owner=OWNER, action_type=ACTION, target=lid, payload=payload,
                                       instruction_id=instruction_id,
                                       after_text=approval_text(cand, passed["replay"])))


def decide(gate: ApprovalGate, record: ApprovalRecord, cand: Candidate, decision: str, decided_by: str,
           run_id: str, seed: int) -> DecisionRow:
    if record.target != cand.lesson.lesson_id or cand.provenance.text_sha256 not in record.exact_text_preview:
        raise TextMismatchError(f"approval {record.approval_id} was proposed for {record.target}")
    if decision not in ("APPROVED", "DENIED"):
        raise ValueError(f"decision must be APPROVED or DENIED, got {decision!r}")
    gate.decide(ApprovalDecision(record.approval_id, decision, decided_by))
    ok = decision == "APPROVED"
    return DecisionRow(cand.lesson.lesson_id, "approval", "pass" if ok else "fail",
                       "HUMAN_APPROVED" if ok else "HUMAN_DENIED", "", "", "", "", str(seed), run_id, "", "", "")
