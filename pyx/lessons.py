"""Lesson and Provenance records (spec Section 4) and the append only candidate store.

A Lesson starts as a candidate; poison check, replay and human approval move it
on in later steps. Each record checks its closed sets when it is built. A
Candidate pairs a lesson with its provenance and refuses a provenance whose
text_sha256 is not the hash of the lesson text, so text cannot change after
distill without the change showing. The store is JSONL: an identical repeat is
skipped, a different record under the same lesson_id is refused.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Tuple, Union

from pyx.call_log import TornLogError, _canonical, _sha256

STATUSES = frozenset({"candidate", "rejected", "earned"})
SOURCE_KINDS = frozenset({"graded_failure", "document_text"})
TEXT_CAP = 400
SCOPE = "paper_anatomy"


class LessonError(ValueError):
    """A lesson or provenance record breaks the spec Section 4 rules."""


def make_lesson_id(criterion_id: str, text: str) -> str:
    return f"L_{criterion_id}_{_sha256(text)[:8]}"


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    text: str
    scope: str
    created_from_trace_id: str
    fixes_criterion_id: str
    status: str
    version: int

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise LessonError(f"status {self.status!r} is not one of {sorted(STATUSES)}")
        if not self.text.strip() or len(self.text) > TEXT_CAP:
            raise LessonError(f"text must be 1 to {TEXT_CAP} characters, got {len(self.text)}")


@dataclass(frozen=True)
class Provenance:
    lesson_id: str
    source_trace_id: str
    source_paper_id: str
    source_kind: str
    distiller_model: str
    text_sha256: str
    replay_run_ids: Tuple[str, ...] = ()
    approver: str = ""
    approved_at: str = ""

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise LessonError(f"source_kind {self.source_kind!r} is not one of {sorted(SOURCE_KINDS)}")


@dataclass(frozen=True)
class Candidate:
    lesson: Lesson
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.provenance.lesson_id != self.lesson.lesson_id:
            raise LessonError(f"provenance lesson_id {self.provenance.lesson_id} is not {self.lesson.lesson_id}")
        if self.provenance.text_sha256 != _sha256(self.lesson.text):
            raise LessonError(f"text_sha256 does not match the text of {self.lesson.lesson_id}")

    def to_json(self) -> str:
        return _canonical({"lesson": asdict(self.lesson), "provenance": asdict(self.provenance)})


class CandidateStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def read(self) -> List[Candidate]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").split("\n")
        if lines[-1] != "":
            raise TornLogError(f"{self.path}: line {len(lines)} has no newline (torn write)")
        out = []
        for line in lines[:-1]:
            d = json.loads(line)
            p = dict(d["provenance"], replay_run_ids=tuple(d["provenance"]["replay_run_ids"]))
            out.append(Candidate(Lesson(**d["lesson"]), Provenance(**p)))
        return out

    def append(self, candidate: Candidate) -> bool:
        for old in self.read():
            if old.lesson.lesson_id == candidate.lesson.lesson_id:
                if old == candidate:
                    return False
                raise LessonError(f"conflict: {candidate.lesson.lesson_id} is already stored with other fields")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(candidate.to_json() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
