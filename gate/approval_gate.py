from __future__ import annotations

import difflib
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class DraftOnlyViolationError(PermissionError):
    """Raised when an external send or write is attempted under draft intent."""


class DenialLockError(PermissionError):
    """Raised when a previously denied action is retried without a new user instruction ID."""


class UnapprovedExecutionError(PermissionError):
    """Raised when an external write is executed without an explicit approval decision."""


EXTERNAL_SEND_ACTION_TYPES = frozenset(
    {
        "send_email",
        "send_slack_message",
        "send_chat_message",
        "publish_post",
        "submit_external_form",
        "create_ticket",
        "update_ticket",
        "delete_external_resource",
        "share_external_resource",
    }
)


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_idempotency_key(
    owner: str,
    action_type: str,
    target: str,
    payload: Dict[str, Any],
) -> str:
    raw = f"{owner.strip()}|{action_type.strip()}|{target.strip()}|{canonical_json(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_unified_diff(
    before_text: str,
    after_text: str,
    resource_label: str = "target",
) -> str:
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{resource_label}",
        tofile=f"b/{resource_label}",
    )
    return "".join(diff)


@dataclass(frozen=True)
class ActionProposal:
    owner: str
    action_type: str
    target: str
    payload: Dict[str, Any]
    instruction_id: str
    intent: str = "execute"
    before_text: str = ""
    after_text: str = ""
    triggered_by_untrusted: bool = False


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    action_id: str
    idempotency_key: str
    owner: str
    action_type: str
    target: str
    instruction_id: str
    intent: str
    exact_text_preview: str
    unified_diff: str
    status: str
    created_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    denial_reason: Optional[str] = None


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    decision: str
    decided_by: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class ExecutionResult:
    action_id: str
    approval_id: str
    idempotency_key: str
    executed: bool
    deduplicated_retry: bool
    output: Dict[str, Any]


@dataclass(frozen=True)
class AuditLogEntry:
    entry_id: int
    event_type: str
    action_id: str
    idempotency_key: str
    actor: str
    details: Dict[str, Any]
    created_at: str


class ApprovalGate:
    """
    Exact-text approval gate enforcing:
    1. Exact-text preview and unified diff generation.
    2. Deterministic SHA-256 idempotency key over (owner, action_type, target, canonical payload).
    3. Strict draft-only send blocking when intent == 'draft'.
    4. Hard denial lock until a new user instruction_id is issued.
    5. Append-only SQLite audit log for all proposals, decisions, and executions.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE NOT NULL,
                owner TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                instruction_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                executed INTEGER NOT NULL DEFAULT 0,
                execution_output_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                owner TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT NOT NULL,
                instruction_id TEXT NOT NULL,
                intent TEXT NOT NULL,
                exact_text_preview TEXT NOT NULL,
                unified_diff TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                denial_reason TEXT,
                FOREIGN KEY(action_id) REFERENCES actions(action_id)
            );

            CREATE TABLE IF NOT EXISTS denial_locks (
                idempotency_key TEXT PRIMARY KEY,
                denied_instruction_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target TEXT NOT NULL,
                reason TEXT,
                locked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                action_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                actor TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_audit(
        self,
        event_type: str,
        action_id: str,
        idempotency_key: str,
        actor: str,
        details: Dict[str, Any],
    ) -> None:
        now = self._now_iso()
        self._conn.execute(
            """
            INSERT INTO audit_log (event_type, action_id, idempotency_key, actor, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, action_id, idempotency_key, actor, canonical_json(details), now),
        )
        self._conn.commit()

    def _format_exact_preview(self, proposal: ActionProposal) -> str:
        lines = [
            f"Owner: {proposal.owner}",
            f"Action: {proposal.action_type}",
            f"Target: {proposal.target}",
            f"Instruction ID: {proposal.instruction_id}",
            f"Intent: {proposal.intent}",
            f"Payload: {canonical_json(proposal.payload)}",
        ]
        if proposal.after_text:
            lines.append(f"Body:\n{proposal.after_text}")
        return "\n".join(lines)

    def propose(self, proposal: ActionProposal) -> ApprovalRecord:
        idempotency_key = compute_idempotency_key(
            owner=proposal.owner,
            action_type=proposal.action_type,
            target=proposal.target,
            payload=proposal.payload,
        )

        if proposal.intent.lower() == "draft" and proposal.action_type in EXTERNAL_SEND_ACTION_TYPES:
            self._append_audit(
                event_type="draft_only_blocked",
                action_id="blocked",
                idempotency_key=idempotency_key,
                actor=proposal.owner,
                details={
                    "action_type": proposal.action_type,
                    "target": proposal.target,
                    "intent": proposal.intent,
                    "instruction_id": proposal.instruction_id,
                },
            )
            raise DraftOnlyViolationError(
                f"External send action '{proposal.action_type}' to '{proposal.target}' is blocked because intent is 'draft'."
            )

        lock_row = self._conn.execute(
            "SELECT * FROM denial_locks WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if lock_row is not None:
            if lock_row["denied_instruction_id"] == proposal.instruction_id:
                self._append_audit(
                    event_type="denial_lock_blocked",
                    action_id="locked",
                    idempotency_key=idempotency_key,
                    actor=proposal.owner,
                    details={
                        "denied_instruction_id": lock_row["denied_instruction_id"],
                        "attempted_instruction_id": proposal.instruction_id,
                        "target": proposal.target,
                    },
                )
                raise DenialLockError(
                    f"Action '{proposal.action_type}' on '{proposal.target}' is locked after denial under instruction '{proposal.instruction_id}'. A new user instruction ID is required."
                )
            else:
                self._conn.execute(
                    "DELETE FROM denial_locks WHERE idempotency_key = ?",
                    (idempotency_key,),
                )
                self._conn.commit()

        existing_approval = self._conn.execute(
            """
            SELECT * FROM approvals
            WHERE idempotency_key = ? AND instruction_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (idempotency_key, proposal.instruction_id),
        ).fetchone()
        if existing_approval is not None:
            return self._row_to_approval(existing_approval)

        now = self._now_iso()
        existing_action = self._conn.execute(
            "SELECT action_id FROM actions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing_action is not None:
            action_id = existing_action["action_id"]
            self._conn.execute(
                "UPDATE actions SET instruction_id = ?, intent = ? WHERE action_id = ?",
                (proposal.instruction_id, proposal.intent, action_id),
            )
        else:
            action_id = f"act_{uuid.uuid4().hex[:12]}"
            self._conn.execute(
                """
                INSERT INTO actions (
                    action_id, idempotency_key, owner, action_type, target,
                    payload_json, instruction_id, intent, executed, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    action_id,
                    idempotency_key,
                    proposal.owner,
                    proposal.action_type,
                    proposal.target,
                    canonical_json(proposal.payload),
                    proposal.instruction_id,
                    proposal.intent,
                    now,
                ),
            )

        approval_id = f"apr_{uuid.uuid4().hex[:12]}"
        after_body = proposal.after_text or str(proposal.payload.get("body", ""))
        diff_text = build_unified_diff(
            before_text=proposal.before_text,
            after_text=after_body,
            resource_label=proposal.target,
        )
        exact_preview = self._format_exact_preview(proposal)

        self._conn.execute(
            """
            INSERT INTO approvals (
                approval_id, action_id, idempotency_key, owner, action_type, target,
                instruction_id, intent, exact_text_preview, unified_diff, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                approval_id,
                action_id,
                idempotency_key,
                proposal.owner,
                proposal.action_type,
                proposal.target,
                proposal.instruction_id,
                proposal.intent,
                exact_preview,
                diff_text,
                now,
            ),
        )
        self._conn.commit()

        self._append_audit(
            event_type="action_proposed",
            action_id=action_id,
            idempotency_key=idempotency_key,
            actor=proposal.owner,
            details={
                "approval_id": approval_id,
                "action_type": proposal.action_type,
                "target": proposal.target,
                "instruction_id": proposal.instruction_id,
            },
        )

        row = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        return self._row_to_approval(row)

    def decide(self, decision: ApprovalDecision) -> ApprovalRecord:
        normalized = decision.decision.strip().upper()
        if normalized not in {"APPROVED", "DENIED"}:
            raise ValueError(f"Unsupported approval decision '{decision.decision}'. Expected APPROVED or DENIED.")

        row = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (decision.approval_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Approval '{decision.approval_id}' not found.")

        now = self._now_iso()
        self._conn.execute(
            """
            UPDATE approvals
            SET status = ?, decided_at = ?, decided_by = ?, denial_reason = ?
            WHERE approval_id = ?
            """,
            (normalized, now, decision.decided_by, decision.reason, decision.approval_id),
        )

        if normalized == "DENIED":
            self._conn.execute(
                """
                INSERT OR REPLACE INTO denial_locks (
                    idempotency_key, denied_instruction_id, owner, action_type, target, reason, locked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["idempotency_key"],
                    row["instruction_id"],
                    row["owner"],
                    row["action_type"],
                    row["target"],
                    decision.reason or "Denied by user",
                    now,
                ),
            )

        self._conn.commit()
        self._append_audit(
            event_type=f"approval_{normalized.lower()}",
            action_id=row["action_id"],
            idempotency_key=row["idempotency_key"],
            actor=decision.decided_by,
            details={
                "approval_id": decision.approval_id,
                "decision": normalized,
                "reason": decision.reason,
            },
        )

        updated = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (decision.approval_id,),
        ).fetchone()
        return self._row_to_approval(updated)

    def execute_approved(
        self,
        approval_id: str,
        executor_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> ExecutionResult:
        approval_row = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if approval_row is None:
            raise KeyError(f"Approval '{approval_id}' not found.")

        status = approval_row["status"]
        idempotency_key = approval_row["idempotency_key"]
        action_id = approval_row["action_id"]

        if status == "DENIED":
            raise DenialLockError(
                f"Cannot execute approval '{approval_id}' because it was DENIED and is locked."
            )
        if status != "APPROVED":
            raise UnapprovedExecutionError(
                f"Cannot execute approval '{approval_id}' with status '{status}'. Explicit APPROVED state required."
            )

        action_row = self._conn.execute(
            "SELECT * FROM actions WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        if action_row["executed"] == 1:
            cached_output = json.loads(action_row["execution_output_json"] or "{}")
            self._append_audit(
                event_type="execution_deduplicated_retry",
                action_id=action_id,
                idempotency_key=idempotency_key,
                actor=approval_row["owner"],
                details={"approval_id": approval_id, "deduplicated": True},
            )
            return ExecutionResult(
                action_id=action_id,
                approval_id=approval_id,
                idempotency_key=idempotency_key,
                executed=True,
                deduplicated_retry=True,
                output=cached_output,
            )

        payload = json.loads(action_row["payload_json"])
        if executor_fn is not None:
            output = executor_fn(payload)
        else:
            output = {
                "status": "dispatched",
                "target": approval_row["target"],
                "action_type": approval_row["action_type"],
                "idempotency_key": idempotency_key,
            }

        self._conn.execute(
            "UPDATE actions SET executed = 1, execution_output_json = ? WHERE action_id = ?",
            (canonical_json(output), action_id),
        )
        self._conn.commit()

        self._append_audit(
            event_type="action_executed",
            action_id=action_id,
            idempotency_key=idempotency_key,
            actor=approval_row["owner"],
            details={"approval_id": approval_id, "output": output},
        )

        return ExecutionResult(
            action_id=action_id,
            approval_id=approval_id,
            idempotency_key=idempotency_key,
            executed=True,
            deduplicated_retry=False,
            output=output,
        )

    def list_pending_approvals(self) -> List[ApprovalRecord]:
        rows = self._conn.execute(
            "SELECT * FROM approvals WHERE status = 'PENDING' ORDER BY created_at ASC"
        ).fetchall()
        return [self._row_to_approval(r) for r in rows]

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        row = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Approval '{approval_id}' not found.")
        return self._row_to_approval(row)

    def list_audit_log(self) -> List[AuditLogEntry]:
        rows = self._conn.execute(
            "SELECT * FROM audit_log ORDER BY entry_id ASC"
        ).fetchall()
        return [
            AuditLogEntry(
                entry_id=r["entry_id"],
                event_type=r["event_type"],
                action_id=r["action_id"],
                idempotency_key=r["idempotency_key"],
                actor=r["actor"],
                details=json.loads(r["details_json"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_approval(row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            action_id=row["action_id"],
            idempotency_key=row["idempotency_key"],
            owner=row["owner"],
            action_type=row["action_type"],
            target=row["target"],
            instruction_id=row["instruction_id"],
            intent=row["intent"],
            exact_text_preview=row["exact_text_preview"],
            unified_diff=row["unified_diff"],
            status=row["status"],
            created_at=row["created_at"],
            decided_at=row["decided_at"],
            decided_by=row["decided_by"],
            denial_reason=row["denial_reason"],
        )
