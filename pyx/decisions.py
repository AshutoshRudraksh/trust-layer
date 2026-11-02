"""Rows for decisions.tsv, the public log of every grade and verdict.

Columns are the ten from spec Section 4 in spec order, then two trailing
amendments: `flags` (JUDGE_DISAGREE, JUDGE_UNAVAILABLE) and `task_id` (which
task a grade row is about). Every specced column keeps its position. See
docs/decisions_tsv.md. Reason codes are the frozen six and nothing else; an
INCONCLUSIVE grade is written as result inconclusive with an empty reason code
and the flag JUDGE_UNAVAILABLE. Every row is validated when it is built.
"""
from __future__ import annotations

import fcntl
import os
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path
from typing import List, Optional, Sequence, Union

from pyx.checker import FAIL
from pyx.judges import INCONCLUSIVE, JUDGE_DISAGREE, JUDGE_UNAVAILABLE, GradeReport, JudgedVerdict

COLUMNS = ("lesson_id", "step", "result", "reason_code", "criteria_fixed", "criteria_broken",
           "judge_a", "judge_b", "seed", "run_id", "flags", "task_id")
REASON_CODES = frozenset({"UNTRUSTED_SOURCE", "NO_FIX", "REGRESSION", "JUDGE_DISAGREE",
                          "HUMAN_DENIED", "HUMAN_APPROVED"})
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "runs" / "decisions.tsv"
HEADER = "\t".join(COLUMNS)
RESULTS = frozenset({"pass", "fail", "inconclusive"})
STEPS = frozenset({"poison", "replay", "approval", "grade"})


class DecisionRowError(ValueError):
    """A decisions.tsv row breaks the schema; the message names the column."""


@dataclass(frozen=True)
class DecisionRow:
    lesson_id: str
    step: str
    result: str
    reason_code: str
    criteria_fixed: str
    criteria_broken: str
    judge_a: str
    judge_b: str
    seed: str
    run_id: str
    flags: str
    task_id: str

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, str) or any(c in value for c in "\t\n\r"):
                raise DecisionRowError(f"{f.name}: must be a string with no tab or newline")
        if self.reason_code and self.reason_code not in REASON_CODES:
            raise DecisionRowError(f"reason_code: {self.reason_code!r} is not a frozen reason code")
        if self.result not in RESULTS:
            raise DecisionRowError(f"result: {self.result!r} is not one of {sorted(RESULTS)}")
        if self.step not in STEPS:
            raise DecisionRowError(f"step: {self.step!r} is not one of {sorted(STEPS)}")
        if self.result == "inconclusive" and (self.reason_code or JUDGE_UNAVAILABLE not in self.flags.split(",")):
            raise DecisionRowError("reason_code: an inconclusive row needs an empty reason code and the flag "
                                   "JUDGE_UNAVAILABLE")

    def values(self) -> List[str]:
        return [getattr(self, c) for c in COLUMNS]


def rows_from_grade(report: GradeReport, run_id: str, seed: int) -> List[DecisionRow]:
    """One grade row per graded answer."""
    judged = [v for v in report.verdicts if isinstance(v, JudgedVerdict)]
    broken = [v.criterion_id for v in report.verdicts if v.status == FAIL]
    flags = [f for f in (JUDGE_DISAGREE, JUDGE_UNAVAILABLE) if any(f in v.flags for v in judged)]
    if broken:
        result = "fail"
    elif any(v.status == INCONCLUSIVE for v in report.verdicts):
        result = "inconclusive"
    else:
        result = "pass"
    return [DecisionRow(
        lesson_id="", step="grade", result=result,
        reason_code=JUDGE_DISAGREE if JUDGE_DISAGREE in flags else "",
        criteria_fixed="", criteria_broken=",".join(broken),
        judge_a=",".join(f"{v.criterion_id}={v.judge_a.verdict}" for v in judged),
        judge_b=",".join(f"{v.criterion_id}={v.judge_b.verdict}" for v in judged),
        seed=str(seed), run_id=run_id, flags=",".join(flags), task_id=report.task_id,
    )]


class DecisionLog:
    """decisions.tsv on disk. Appends run under an flock and replace the file by
    temp file, fsync and rename, so a crash leaves the old file whole. A row
    identical in every column to one already present is skipped. A file whose
    header differs from COLUMNS is refused, never rewritten."""

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_PATH

    def _lines(self) -> List[str]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if lines and lines[0] != HEADER:
            raise DecisionRowError(f"header: {self.path} does not start with the decisions.tsv header")
        return lines[1:]

    def read(self) -> List[DecisionRow]:
        rows = []
        for number, line in enumerate(self._lines(), start=2):
            parts = line.split("\t")
            try:
                if len(parts) != len(COLUMNS):
                    raise DecisionRowError(f"has {len(parts)} columns, expected {len(COLUMNS)}")
                rows.append(DecisionRow(*parts))
            except DecisionRowError as exc:
                raise DecisionRowError(f"line {number}: {exc}") from exc
        return rows

    def append(self, rows: Sequence[DecisionRow]) -> int:
        """Write rows not already present; returns how many were added."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_name(self.path.name + ".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            existing = self._lines()
            seen = set(existing)
            new = []
            for row in rows:
                line = "\t".join(row.values())
                if line not in seen:
                    seen.add(line)
                    new.append(line)
            if not new:
                return 0
            fd, tmp = tempfile.mkstemp(prefix=".decisions.", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write("\n".join([HEADER, *existing, *new]) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
            return len(new)
