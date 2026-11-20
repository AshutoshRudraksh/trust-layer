"""execute_approved() must honor denial_locks even if approvals.status is forced to APPROVED."""
from __future__ import annotations

import pytest

from gate.approval_gate import (
    ActionProposal,
    ApprovalDecision,
    ApprovalGate,
    DenialLockError,
)


def _proposal(instruction_id: str, **kwargs: object) -> ActionProposal:
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


def _executed_flag(gate: ApprovalGate, action_id: str) -> int:
    row = gate._conn.execute(
        "SELECT executed FROM actions WHERE action_id = ?",
        (action_id,),
    ).fetchone()
    assert row is not None
    return int(row["executed"])


def test_execute_refuses_when_denial_lock_matches_instruction_even_if_status_forced_approved() -> None:
    gate = ApprovalGate()
    record = gate.propose(_proposal("instr_same"))
    gate.decide(
        ApprovalDecision(
            approval_id=record.approval_id,
            decision="DENIED",
            decided_by="user_1",
            reason="no",
        )
    )
    gate._conn.execute(
        "UPDATE approvals SET status = 'APPROVED' WHERE approval_id = ?",
        (record.approval_id,),
    )
    gate._conn.commit()
    assert gate.get_approval(record.approval_id).status == "APPROVED"

    calls = {"n": 0}

    def executor(payload: dict) -> dict:
        calls["n"] += 1
        return {"ok": True}

    with pytest.raises(DenialLockError):
        gate.execute_approved(record.approval_id, executor_fn=executor)
    assert calls["n"] == 0
    assert _executed_flag(gate, record.action_id) == 0


def test_execute_allows_a_new_instruction_on_the_same_idempotency_key() -> None:
    gate = ApprovalGate()
    first = gate.propose(_proposal("instr_old"))
    gate.decide(
        ApprovalDecision(
            approval_id=first.approval_id,
            decision="DENIED",
            decided_by="user_1",
            reason="no",
        )
    )
    second = gate.propose(_proposal("instr_new"))
    assert second.idempotency_key == first.idempotency_key
    assert second.instruction_id == "instr_new"
    assert second.approval_id != first.approval_id
    gate.decide(
        ApprovalDecision(
            approval_id=second.approval_id,
            decision="APPROVED",
            decided_by="user_1",
        )
    )

    calls = {"n": 0}

    def executor(payload: dict) -> dict:
        calls["n"] += 1
        return {"ok": True}

    result = gate.execute_approved(second.approval_id, executor_fn=executor)
    assert calls["n"] == 1
    assert result.executed is True
    assert _executed_flag(gate, second.action_id) == 1
