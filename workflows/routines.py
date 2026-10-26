from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


@dataclass(frozen=True)
class NudgeRecord:
    routine_id: str
    item_key: str
    agent_id: str
    summary: str
    emitted: bool
    suppressed_by_cooldown: bool
    emitted_at: str
    next_allowed_at: str


class RoutineCooldownRunner:
    """
    Durable workflow routine runner enforcing a 24-hour anti-spam nudge cooldown
    per (routine_id, item_key) so recurring background checks never spam the user.
    """

    def __init__(self, cooldown_hours: int = 24) -> None:
        self.cooldown_hours = cooldown_hours
        self._last_emitted: Dict[str, datetime] = {}
        self._history: List[NudgeRecord] = []

    def trigger_nudge(
        self,
        routine_id: str,
        item_key: str,
        agent_id: str,
        summary: str,
        now: Optional[datetime] = None,
    ) -> NudgeRecord:
        current_time = now or datetime.now(timezone.utc)
        composite_key = f"{routine_id}:{item_key}"
        last_time = self._last_emitted.get(composite_key)
        cooldown_delta = timedelta(hours=self.cooldown_hours)

        if last_time is not None and (current_time - last_time) < cooldown_delta:
            next_allowed = (last_time + cooldown_delta).isoformat()
            record = NudgeRecord(
                routine_id=routine_id,
                item_key=item_key,
                agent_id=agent_id,
                summary=summary,
                emitted=False,
                suppressed_by_cooldown=True,
                emitted_at=current_time.isoformat(),
                next_allowed_at=next_allowed,
            )
            self._history.append(record)
            return record

        self._last_emitted[composite_key] = current_time
        next_allowed = (current_time + cooldown_delta).isoformat()
        record = NudgeRecord(
            routine_id=routine_id,
            item_key=item_key,
            agent_id=agent_id,
            summary=summary,
            emitted=True,
            suppressed_by_cooldown=False,
            emitted_at=current_time.isoformat(),
            next_allowed_at=next_allowed,
        )
        self._history.append(record)
        return record

    def list_history(self) -> List[NudgeRecord]:
        return list(self._history)
