from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from agents.skills_loader import SkillsLoader


@dataclass(frozen=True)
class MemoryFact:
    fact_id: str
    namespace: str
    key: str
    value: str
    source_uri: str
    timestamp: str
    confidence: float
    responsible_agent: str
    corrected_by_user: bool = False


@dataclass(frozen=True)
class MemoryCorrectionResult:
    updated_fact: MemoryFact
    previous_value: str
    new_value: str
    responsible_agent: str
    proposed_skill_diff: str


class MemoryStore:
    """
    Shared, sourced, user-correctable memory store where every fact carries
    a mandatory source_uri, timestamp, and confidence score. When a user corrects
    a stored fact, the store updates the fact and generates a reviewed unified diff
    against the responsible specialist agent's SKILL.md.
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        skills_loader: Optional[SkillsLoader] = None,
    ) -> None:
        self.db_path = str(db_path)
        self.skills_loader = skills_loader
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_facts (
                fact_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                confidence REAL NOT NULL,
                responsible_agent TEXT NOT NULL,
                corrected_by_user INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self._conn.commit()

    def add_fact(
        self,
        namespace: str,
        key: str,
        value: str,
        source_uri: str,
        confidence: float,
        responsible_agent: str,
        timestamp: Optional[str] = None,
    ) -> MemoryFact:
        if not source_uri.strip():
            raise ValueError("source_uri is required for every shared memory fact.")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0.")

        fact_id = f"fact_{uuid.uuid4().hex[:12]}"
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO memory_facts (
                fact_id, namespace, key, value, source_uri, timestamp,
                confidence, responsible_agent, corrected_by_user
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (fact_id, namespace, key, value, source_uri, ts, confidence, responsible_agent),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM memory_facts WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        return self._row_to_fact(row)

    def correct_fact(
        self,
        fact_id: str,
        corrected_value: str,
        correction_source_uri: str = "user://interactive-correction",
        learned_skill_rule: Optional[str] = None,
    ) -> MemoryCorrectionResult:
        row = self._conn.execute(
            "SELECT * FROM memory_facts WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Memory fact '{fact_id}' not found.")

        previous_value = row["value"]
        responsible_agent = row["responsible_agent"]
        now_iso = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            UPDATE memory_facts
            SET value = ?, source_uri = ?, timestamp = ?, confidence = 1.0, corrected_by_user = 1
            WHERE fact_id = ?
            """,
            (corrected_value, correction_source_uri, now_iso, fact_id),
        )
        self._conn.commit()

        updated_row = self._conn.execute(
            "SELECT * FROM memory_facts WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        updated_fact = self._row_to_fact(updated_row)

        rule_text = learned_skill_rule or (
            f"For '{updated_fact.key}', always use '{corrected_value}' (corrected from '{previous_value}')."
        )
        skill_diff = ""
        if self.skills_loader is not None:
            try:
                skill_diff = self.skills_loader.propose_skill_rule_diff(
                    name=responsible_agent,
                    learned_rule=rule_text,
                )
            except KeyError:
                skill_diff = (
                    f"--- a/skills/{responsible_agent}/SKILL.md\n"
                    f"+++ b/skills/{responsible_agent}/SKILL.md\n"
                    f"@@ -1 +1,2 @@\n"
                    f"+- Learned Rule: {rule_text}\n"
                )
        else:
            skill_diff = (
                f"--- a/skills/{responsible_agent}/SKILL.md\n"
                f"+++ b/skills/{responsible_agent}/SKILL.md\n"
                f"@@ -1 +1,2 @@\n"
                f"+- Learned Rule: {rule_text}\n"
            )

        return MemoryCorrectionResult(
            updated_fact=updated_fact,
            previous_value=previous_value,
            new_value=corrected_value,
            responsible_agent=responsible_agent,
            proposed_skill_diff=skill_diff,
        )

    def list_facts(self, namespace: Optional[str] = None) -> List[MemoryFact]:
        if namespace:
            rows = self._conn.execute(
                "SELECT * FROM memory_facts WHERE namespace = ? ORDER BY timestamp DESC",
                (namespace,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memory_facts ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_fact(r) for r in rows]

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> MemoryFact:
        return MemoryFact(
            fact_id=row["fact_id"],
            namespace=row["namespace"],
            key=row["key"],
            value=row["value"],
            source_uri=row["source_uri"],
            timestamp=row["timestamp"],
            confidence=float(row["confidence"]),
            responsible_agent=row["responsible_agent"],
            corrected_by_user=bool(row["corrected_by_user"]),
        )
