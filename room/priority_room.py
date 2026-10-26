from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from gate.approval_gate import ApprovalGate
from locks.owner_registry import OwnerRegistry


@dataclass
class PriorityItem:
    item_id: str
    category: str
    title: str
    owner_agent: str
    priority_score: int
    resource_key: str
    requires_approval: bool = False
    approval_id: Optional[str] = None
    exact_text_preview: Optional[str] = None
    unified_diff: Optional[str] = None
    routed_notes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PriorityRoomMerger:
    """
    Merges pending approval cards, active single-owner task locks, and agent findings
    into one deduplicated, priority-ranked feed for the user's Priority Room.
    """

    def __init__(self, gate: ApprovalGate, locks: OwnerRegistry) -> None:
        self.gate = gate
        self.locks = locks
        self._custom_items: Dict[str, PriorityItem] = {}

    def publish_finding(self, item: PriorityItem) -> None:
        existing = self._custom_items.get(item.resource_key)
        if existing is None or item.priority_score > existing.priority_score:
            self._custom_items[item.resource_key] = item

    def build_priority_list(self) -> List[Dict[str, Any]]:
        merged: Dict[str, PriorityItem] = {}

        for approval in self.gate.list_pending_approvals():
            key = f"approval:{approval.idempotency_key}"
            merged[key] = PriorityItem(
                item_id=approval.approval_id,
                category="pending_approval",
                title=f"Approve {approval.action_type} on {approval.target}",
                owner_agent=approval.owner,
                priority_score=100,
                resource_key=approval.target,
                requires_approval=True,
                approval_id=approval.approval_id,
                exact_text_preview=approval.exact_text_preview,
                unified_diff=approval.unified_diff,
            )

        for lock in self.locks.list_active_locks():
            key = f"lock:{lock.resource_key}"
            score = 80 if lock.routed_context else 60
            merged[key] = PriorityItem(
                item_id=f"lock_{lock.resource_key}",
                category="active_task_lock",
                title=lock.task_summary,
                owner_agent=lock.owner_agent,
                priority_score=score,
                resource_key=lock.resource_key,
                requires_approval=False,
                routed_notes=lock.routed_context,
            )

        for res_key, item in self._custom_items.items():
            key = f"finding:{res_key}"
            merged[key] = item

        ordered = sorted(
            merged.values(),
            key=lambda x: (-x.priority_score, x.item_id),
        )
        return [item.to_dict() for item in ordered]
