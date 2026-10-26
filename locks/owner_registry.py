from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class OwnerLockRecord:
    resource_key: str
    owner_agent: str
    task_summary: str
    acquired_at: str
    expires_at: str
    routed_context: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class LockClaimResult:
    acquired: bool
    resource_key: str
    owner_agent: str
    requesting_agent: str
    conflict_routed_to_priority_room: bool
    message: str
    lock_record: OwnerLockRecord


class OwnerRegistry:
    """
    Single-owner task lock registry ensuring two specialist agents never duplicate
    the same action, hold, or nudge. When a second specialist agent attempts to claim
    an already locked resource, it receives a structured conflict result and its context
    is routed to the consolidated priority room without generating a duplicate nudge.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS owner_locks (
                resource_key TEXT PRIMARY KEY,
                owner_agent TEXT NOT NULL,
                task_summary TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                routed_context_json TEXT NOT NULL DEFAULT '[]'
            );
            """
        )
        self._conn.commit()

    def claim(
        self,
        resource_key: str,
        agent_id: str,
        task_summary: str,
        ttl_seconds: int = 3600,
        context_note: Optional[str] = None,
    ) -> LockClaimResult:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(seconds=ttl_seconds)).isoformat()

        existing = self._conn.execute(
            "SELECT * FROM owner_locks WHERE resource_key = ?",
            (resource_key,),
        ).fetchone()

        if existing is not None:
            existing_expires = datetime.fromisoformat(existing["expires_at"])
            if existing_expires > now and existing["owner_agent"] != agent_id:
                routed = json.loads(existing["routed_context_json"] or "[]")
                routed.append(
                    {
                        "from_agent": agent_id,
                        "task_summary": task_summary,
                        "context_note": context_note or task_summary,
                        "routed_at": now_iso,
                    }
                )
                self._conn.execute(
                    "UPDATE owner_locks SET routed_context_json = ? WHERE resource_key = ?",
                    (json.dumps(routed), resource_key),
                )
                self._conn.commit()
                updated_row = self._conn.execute(
                    "SELECT * FROM owner_locks WHERE resource_key = ?",
                    (resource_key,),
                ).fetchone()
                record = self._row_to_record(updated_row)
                return LockClaimResult(
                    acquired=False,
                    resource_key=resource_key,
                    owner_agent=record.owner_agent,
                    requesting_agent=agent_id,
                    conflict_routed_to_priority_room=True,
                    message=(
                        f"Resource '{resource_key}' is already owned by '{record.owner_agent}'. "
                        f"Context from '{agent_id}' was routed to the priority room with zero duplicate nudges."
                    ),
                    lock_record=record,
                )

            if existing["owner_agent"] == agent_id:
                self._conn.execute(
                    """
                    UPDATE owner_locks
                    SET task_summary = ?, expires_at = ?
                    WHERE resource_key = ?
                    """,
                    (task_summary, expires_iso, resource_key),
                )
                self._conn.commit()
                updated_row = self._conn.execute(
                    "SELECT * FROM owner_locks WHERE resource_key = ?",
                    (resource_key,),
                ).fetchone()
                record = self._row_to_record(updated_row)
                return LockClaimResult(
                    acquired=True,
                    resource_key=resource_key,
                    owner_agent=agent_id,
                    requesting_agent=agent_id,
                    conflict_routed_to_priority_room=False,
                    message=f"Lock on '{resource_key}' renewed by '{agent_id}'.",
                    lock_record=record,
                )

        self._conn.execute(
            """
            INSERT OR REPLACE INTO owner_locks (
                resource_key, owner_agent, task_summary, acquired_at, expires_at, routed_context_json
            )
            VALUES (?, ?, ?, ?, ?, '[]')
            """,
            (resource_key, agent_id, task_summary, now_iso, expires_iso),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM owner_locks WHERE resource_key = ?",
            (resource_key,),
        ).fetchone()
        record = self._row_to_record(row)
        return LockClaimResult(
            acquired=True,
            resource_key=resource_key,
            owner_agent=agent_id,
            requesting_agent=agent_id,
            conflict_routed_to_priority_room=False,
            message=f"Lock on '{resource_key}' acquired by '{agent_id}'.",
            lock_record=record,
        )

    def release(self, resource_key: str, agent_id: str) -> bool:
        row = self._conn.execute(
            "SELECT owner_agent FROM owner_locks WHERE resource_key = ?",
            (resource_key,),
        ).fetchone()
        if row is None or row["owner_agent"] != agent_id:
            return False
        self._conn.execute(
            "DELETE FROM owner_locks WHERE resource_key = ?",
            (resource_key,),
        )
        self._conn.commit()
        return True

    def list_active_locks(self) -> List[OwnerLockRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM owner_locks WHERE expires_at > ? ORDER BY acquired_at ASC",
            (now_iso,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> OwnerLockRecord:
        return OwnerLockRecord(
            resource_key=row["resource_key"],
            owner_agent=row["owner_agent"],
            task_summary=row["task_summary"],
            acquired_at=row["acquired_at"],
            expires_at=row["expires_at"],
            routed_context=json.loads(row["routed_context_json"] or "[]"),
        )
