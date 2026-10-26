from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents.meta_client import MetaModelClient
from agents.skills_loader import SkillsLoader
from gate.approval_gate import (
    ActionProposal,
    ApprovalDecision,
    ApprovalGate,
    DenialLockError,
    DraftOnlyViolationError,
    UnapprovedExecutionError,
)
from isolation.untrusted_guard import UntrustedDataGuard, UntrustedExecutionBlockedError
from locks.owner_registry import OwnerRegistry
from memory.memory_store import MemoryStore
from room.priority_room import PriorityRoomMerger


class ProposeActionRequest(BaseModel):
    owner: str
    action_type: str
    target: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    instruction_id: str
    intent: str = "execute"
    before_text: str = ""
    after_text: str = ""
    triggered_by_untrusted: bool = False
    untrusted_source: Optional[str] = None
    untrusted_raw_text: Optional[str] = None


class DecideApprovalRequest(BaseModel):
    decision: str
    decided_by: str
    reason: Optional[str] = None


class ClaimLockRequest(BaseModel):
    resource_key: str
    agent_id: str
    task_summary: str
    ttl_seconds: int = 3600
    context_note: Optional[str] = None


class AddMemoryFactRequest(BaseModel):
    namespace: str
    key: str
    value: str
    source_uri: str
    confidence: float = 0.95
    responsible_agent: str = "research"


class CorrectMemoryFactRequest(BaseModel):
    fact_id: str
    corrected_value: str
    correction_source_uri: str = "user://interactive-correction"
    learned_skill_rule: Optional[str] = None


def create_app(db_path: str = ":memory:") -> FastAPI:
    app = FastAPI(
        title="Trust Layer Multi-Agent Execution API",
        version="0.1.0",
        description="Open-source trust-first multi-agent execution layer powered by the Meta Model API.",
    )

    skills_root = Path(__file__).resolve().parent.parent / "skills"
    skills_loader = SkillsLoader(skills_root=skills_root)
    gate = ApprovalGate(db_path=db_path)
    locks = OwnerRegistry(db_path=db_path)
    guard = UntrustedDataGuard()
    memory = MemoryStore(db_path=db_path, skills_loader=skills_loader)
    room = PriorityRoomMerger(gate=gate, locks=locks)
    meta_client = MetaModelClient()

    app.state.gate = gate
    app.state.locks = locks
    app.state.guard = guard
    app.state.memory = memory
    app.state.room = room
    app.state.skills_loader = skills_loader
    app.state.meta_client = meta_client

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "skills_loaded": [s.name for s in skills_loader.list_frontmatter()],
            "budget_cap_usd": meta_client.budget_cap_usd,
            "cumulative_spend_usd": meta_client.cumulative_spend_usd,
        }

    @app.post("/actions/propose")
    def propose_action(req: ProposeActionRequest) -> Dict[str, Any]:
        if req.triggered_by_untrusted:
            envelope = guard.wrap(
                raw_text=req.untrusted_raw_text or "",
                source=req.untrusted_source or "external_source",
            )
            try:
                guard.assert_action_allowed(
                    envelope=envelope,
                    action_type=req.action_type,
                    target=req.target,
                    explicit_user_approval=False,
                )
            except UntrustedExecutionBlockedError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc

        proposal = ActionProposal(
            owner=req.owner,
            action_type=req.action_type,
            target=req.target,
            payload=req.payload,
            instruction_id=req.instruction_id,
            intent=req.intent,
            before_text=req.before_text,
            after_text=req.after_text,
            triggered_by_untrusted=req.triggered_by_untrusted,
        )
        try:
            record = gate.propose(proposal)
            return asdict(record)
        except DraftOnlyViolationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except DenialLockError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/approvals/{approval_id}/decide")
    def decide_approval(approval_id: str, req: DecideApprovalRequest) -> Dict[str, Any]:
        try:
            record = gate.decide(
                ApprovalDecision(
                    approval_id=approval_id,
                    decision=req.decision,
                    decided_by=req.decided_by,
                    reason=req.reason,
                )
            )
            return asdict(record)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/approvals/{approval_id}/execute")
    def execute_approval(approval_id: str) -> Dict[str, Any]:
        try:
            res = gate.execute_approved(approval_id=approval_id)
            return asdict(res)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (DenialLockError, UnapprovedExecutionError) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.get("/locks")
    def list_locks() -> Dict[str, Any]:
        return {"locks": [asdict(l) for l in locks.list_active_locks()]}

    @app.post("/locks/claim")
    def claim_lock(req: ClaimLockRequest) -> Dict[str, Any]:
        result = locks.claim(
            resource_key=req.resource_key,
            agent_id=req.agent_id,
            task_summary=req.task_summary,
            ttl_seconds=req.ttl_seconds,
            context_note=req.context_note,
        )
        return asdict(result)

    @app.get("/memory/facts")
    def list_memory_facts(namespace: Optional[str] = None) -> Dict[str, Any]:
        return {"facts": [asdict(f) for f in memory.list_facts(namespace=namespace)]}

    @app.post("/memory/facts")
    def add_memory_fact(req: AddMemoryFactRequest) -> Dict[str, Any]:
        try:
            fact = memory.add_fact(
                namespace=req.namespace,
                key=req.key,
                value=req.value,
                source_uri=req.source_uri,
                confidence=req.confidence,
                responsible_agent=req.responsible_agent,
            )
            return asdict(fact)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/memory/correct")
    def correct_memory_fact(req: CorrectMemoryFactRequest) -> Dict[str, Any]:
        try:
            result = memory.correct_fact(
                fact_id=req.fact_id,
                corrected_value=req.corrected_value,
                correction_source_uri=req.correction_source_uri,
                learned_skill_rule=req.learned_skill_rule,
            )
            return asdict(result)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/room/priority-list")
    def get_priority_list() -> Dict[str, Any]:
        return {"items": room.build_priority_list()}

    return app


app = create_app()
