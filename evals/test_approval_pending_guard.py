"""decide() must refuse a non-PENDING approval; a denial cannot be overwritten and then executed.

There is no EXPIRED (or EXECUTED) status in the gate: approvals stay PENDING, APPROVED, or
DENIED as plain strings. After execution the approval row stays APPROVED and actions.executed
is set to 1, so the executed case is covered by re-deciding that APPROVED row.
"""
from __future__ import annotations

from pathlib import Path
from threading import Barrier, Thread

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from gate.approval_gate import (
    ActionProposal,
    ApprovalDecision,
    ApprovalGate,
    ApprovalNotPendingError,
    DenialLockError,
)
from pyx.approval import decide as pyx_decide, propose as pyx_propose
from pyx.arms import earned_ids
from pyx.decisions import DecisionRow
from pyx.lessons import CandidateStore


def _proposal(instruction_id: str = "instr_guard_1", **kwargs: object) -> ActionProposal:
    fields = dict(
        owner="pipeline",
        action_type="send_email",
        target="partner@example.com",
        payload={"subject": "Release readiness", "body": "All checks passed."},
        instruction_id=instruction_id,
        intent="execute",
        after_text="All checks passed.",
    )
    fields.update(kwargs)
    return ActionProposal(**fields)  # type: ignore[arg-type]


def _decide(gate: ApprovalGate, approval_id: str, decision: str, reason: str | None = None):
    return gate.decide(
        ApprovalDecision(
            approval_id=approval_id,
            decision=decision,
            decided_by="user_1",
            reason=reason,
        )
    )


def _executed_flag(gate: ApprovalGate, action_id: str) -> int:
    row = gate._conn.execute(
        "SELECT executed FROM actions WHERE action_id = ?",
        (action_id,),
    ).fetchone()
    assert row is not None
    return int(row["executed"])


def test_redeciding_denied_to_approved_is_rejected_and_row_stays_denied() -> None:
    gate = ApprovalGate()
    record = gate.propose(_proposal())
    denied = _decide(gate, record.approval_id, "DENIED", reason="Wait for QA")
    assert denied.status == "DENIED"
    with pytest.raises(ApprovalNotPendingError):
        _decide(gate, record.approval_id, "APPROVED")
    assert gate.get_approval(record.approval_id).status == "DENIED"


def test_redeciding_approved_to_denied_is_rejected_and_row_stays_approved() -> None:
    gate = ApprovalGate()
    record = gate.propose(_proposal())
    approved = _decide(gate, record.approval_id, "APPROVED")
    assert approved.status == "APPROVED"
    with pytest.raises(ApprovalNotPendingError):
        _decide(gate, record.approval_id, "DENIED", reason="changed my mind")
    assert gate.get_approval(record.approval_id).status == "APPROVED"


def test_redeciding_an_executed_approval_is_rejected() -> None:
    gate = ApprovalGate()
    record = gate.propose(_proposal())
    _decide(gate, record.approval_id, "APPROVED")
    result = gate.execute_approved(record.approval_id, executor_fn=lambda payload: {"ok": True})
    assert result.executed is True
    assert _executed_flag(gate, record.action_id) == 1
    with pytest.raises(ApprovalNotPendingError):
        _decide(gate, record.approval_id, "DENIED", reason="too late")
    kept = gate.get_approval(record.approval_id)
    assert kept.status == "APPROVED"
    assert _executed_flag(gate, record.action_id) == 1


def test_deny_then_redecide_approved_does_not_call_executor() -> None:
    gate = ApprovalGate()
    record = gate.propose(_proposal())
    _decide(gate, record.approval_id, "DENIED", reason="no")
    with pytest.raises(ApprovalNotPendingError):
        _decide(gate, record.approval_id, "APPROVED")
    assert gate.get_approval(record.approval_id).status == "DENIED"

    calls = {"n": 0}

    def executor(payload: dict) -> dict:
        calls["n"] += 1
        return {"ok": True}

    with pytest.raises(DenialLockError):
        gate.execute_approved(record.approval_id, executor_fn=executor)
    assert calls["n"] == 0
    assert _executed_flag(gate, record.action_id) == 0


def test_decide_raises_when_a_second_update_would_be_a_zero_rowcount() -> None:
    """A second decide must raise rather than silently return success after a no-op UPDATE."""
    gate = ApprovalGate()
    record = gate.propose(_proposal())
    _decide(gate, record.approval_id, "DENIED")
    with pytest.raises(ApprovalNotPendingError):
        _decide(gate, record.approval_id, "DENIED")
    assert gate.get_approval(record.approval_id).status == "DENIED"


def test_concurrent_decides_on_one_pending_approval_have_exactly_one_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "gate.db"
    setup = ApprovalGate(db_path)
    record = setup.propose(_proposal())
    approval_id = record.approval_id
    start = Barrier(2)
    outcomes: list[tuple[str, str | None]] = []

    def worker(decision: str) -> None:
        gate = ApprovalGate(db_path)
        start.wait()
        try:
            updated = _decide(gate, approval_id, decision)
            outcomes.append(("ok", updated.status))
        except ApprovalNotPendingError:
            outcomes.append(("err", None))

    threads = [
        Thread(target=worker, args=("APPROVED",)),
        Thread(target=worker, args=("DENIED",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(kind for kind, _ in outcomes) == ["err", "ok"]
    winners = [status for kind, status in outcomes if kind == "ok"]
    assert winners in (["APPROVED"], ["DENIED"])
    final = ApprovalGate(db_path).get_approval(approval_id)
    assert final.status == winners[0]


def test_http_redecide_returns_409_and_leaves_the_row_denied() -> None:
    app = create_app()
    client = TestClient(app)
    propose_res = client.post(
        "/actions/propose",
        json={
            "owner": "pipeline",
            "action_type": "send_email",
            "target": "ops@example.com",
            "payload": {"subject": "Weekly digest", "body": "System healthy."},
            "instruction_id": "instr_api_guard_1",
            "intent": "execute",
            "after_text": "System healthy.",
        },
    )
    assert propose_res.status_code == 200
    approval_id = propose_res.json()["approval_id"]
    first = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "DENIED", "decided_by": "user_1", "reason": "no"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "DENIED"
    second = client.post(
        f"/approvals/{approval_id}/decide",
        json={"decision": "APPROVED", "decided_by": "user_1"},
    )
    assert second.status_code == 409
    execute_res = client.post(f"/approvals/{approval_id}/execute")
    assert execute_res.status_code == 403


CANDS = CandidateStore(
    Path(__file__).resolve().parent / "fixtures" / "pyx" / "replay" / "e4_distill_candidates.jsonl"
).read()
C = CANDS[0]
LID = C.lesson.lesson_id


def _pyx_rows():
    return [
        DecisionRow(LID, "poison", "pass", "", "", "", "", "", "0", "r1", "", "", "clean"),
        DecisionRow(LID, "replay", "pass", "", "T1.C1", "", "", "", "0", "r1", "", "T1", "clean"),
    ]


def test_a_denied_pyx_lesson_cannot_be_flipped_into_earned_ids() -> None:
    """pyx.approval.decide() is the path that writes the DecisionRow earned_ids() reads."""
    gate = ApprovalGate()
    record = pyx_propose(gate, C, _pyx_rows(), "ins1")
    denied = pyx_decide(gate, record, C, "DENIED", "Ashutosh", "r1", 0)
    assert earned_ids(_pyx_rows() + [denied]) == set()
    with pytest.raises(ApprovalNotPendingError):
        pyx_decide(gate, record, C, "APPROVED", "Ashutosh", "r1", 0)
    assert gate.get_approval(record.approval_id).status == "DENIED"
    assert earned_ids(_pyx_rows() + [denied]) == set()
