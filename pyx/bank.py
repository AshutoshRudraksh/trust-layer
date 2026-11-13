"""The earned lessons bank: a read only view over one run directory.

The bank adds no new definition of earned. A lesson is earned exactly when
pyx.arms.earned_ids says so over the run's decisions.tsv: a poison pass, a
replay pass, and an approval row with reason HUMAN_APPROVED. Lesson texts
and provenance come from the run's candidates files, read through the
existing CandidateStore; verdict rows come from decisions.tsv, read through
the existing DecisionLog; per repetition replay detail comes from
replay_reps.tsv when the run recorded it.

Only an earned lesson is served with its text. Every other candidate,
planted or rejected, is served as its sha256 and verdict rows only, so no
caller of this view can receive text the human gate never admitted.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from pyx.arms import earned_ids
from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import Candidate, CandidateStore


class BankError(ValueError):
    """The run directory cannot serve as a bank, or the lesson is unknown."""


class LessonBank:
    def __init__(self, run_dir: Path, candidates: Sequence[Candidate],
                 rows: Sequence[DecisionRow], replay_reps: Sequence[Dict[str, str]]) -> None:
        self.run_dir = run_dir
        self._candidates = {c.lesson.lesson_id: c for c in candidates}
        self._rows = list(rows)
        self._replay_reps = list(replay_reps)
        self._earned = earned_ids(self._rows)

    @classmethod
    def load(cls, run_dir: Path | str) -> "LessonBank":
        run_dir = Path(run_dir)
        decisions_path = run_dir / "decisions.tsv"
        if not decisions_path.exists():
            raise BankError(f"{run_dir}: no decisions.tsv, not a run directory the bank can serve")
        candidate_files = sorted(run_dir.glob("candidates*.jsonl"))
        if not candidate_files:
            raise BankError(f"{run_dir}: no candidates*.jsonl, nothing to serve")
        candidates: List[Candidate] = []
        for path in candidate_files:
            candidates.extend(CandidateStore(path).read())
        reps: List[Dict[str, str]] = []
        reps_path = run_dir / "replay_reps.tsv"
        if reps_path.exists():
            lines = reps_path.read_text(encoding="utf-8").splitlines()
            if lines:
                header = lines[0].split("\t")
                for line in lines[1:]:
                    if line:
                        reps.append(dict(zip(header, line.split("\t"))))
        return cls(run_dir, candidates, DecisionLog(decisions_path).read(), reps)

    def earned_lessons(self, task_id: Optional[str] = None,
                       criterion_id: Optional[str] = None) -> List[dict]:
        out = []
        for lesson_id in sorted(self._earned):
            candidate = self._candidates.get(lesson_id)
            if candidate is None:
                continue
            lesson = candidate.lesson
            if criterion_id is not None and lesson.fixes_criterion_id != criterion_id:
                continue
            if task_id is not None and lesson.fixes_criterion_id.split(".")[0] != task_id:
                continue
            out.append(_lesson_view(candidate))
        return out

    def provenance(self, lesson_id: str) -> dict:
        candidate = self._candidates.get(lesson_id)
        if candidate is None:
            raise BankError(f"unknown lesson_id {lesson_id!r} in {self.run_dir}")
        view = _lesson_view(candidate)
        earned = lesson_id in self._earned
        if not earned:
            del view["text"]
        view["provenance"] = asdict(candidate.provenance)
        view["earned"] = earned
        view["decisions"] = [asdict(r) for r in self._rows if r.lesson_id == lesson_id]
        view["replay_repetitions"] = [r for r in self._replay_reps if r.get("lesson_id") == lesson_id]
        return view


def _lesson_view(candidate: Candidate) -> dict:
    lesson, provenance = candidate.lesson, candidate.provenance
    return {
        "lesson_id": lesson.lesson_id,
        "text": lesson.text,
        "text_sha256": provenance.text_sha256,
        "fixes_criterion_id": lesson.fixes_criterion_id,
        "task_id": lesson.fixes_criterion_id.split(".")[0],
        "scope": lesson.scope,
        "status": lesson.status,
        "version": lesson.version,
    }
