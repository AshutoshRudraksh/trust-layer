"""The four memory arms (spec Section 6): one context builder each, one layout (Amendment 4).

Every arm returns an ArmContext whose text goes verbatim into the worker prompt's
context section. Arms differ only in content: no memory is empty; raw traces are
earlier answers with their failure view lines (criterion id, type and source
pointer, the same view the distiller gets, never rubric text); free lessons are
every candidate as written; earned lessons are only those with a poison pass, a
replay pass and a HUMAN_APPROVED approval row in decisions.tsv.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Set, Tuple

from pyx.decisions import DecisionRow
from pyx.failure_view import failure_view
from pyx.judges import GradeReport
from pyx.lessons import Candidate

ARMS = ("no_memory", "raw_traces", "free_lessons", "earned_lessons")


@dataclass(frozen=True)
class ArmContext:
    arm: str
    text: str
    lesson_ids: Tuple[str, ...]


def no_memory() -> ArmContext:
    return ArmContext("no_memory", "", ())


def raw_traces(traces: Sequence[Tuple[str, str, GradeReport]]) -> ArmContext:
    """traces: (task_id, answer_text, its GradeReport) from an earlier no memory run."""
    blocks = []
    for task_id, answer, report in traces:
        failed = "\n".join(f"- {f.criterion_id} ({f.type}, {f.source})" for f in failure_view(report))
        blocks.append(f"Earlier answer for {task_id}:\n{answer}\nFailed criteria:\n{failed}")
    return ArmContext("raw_traces", "\n\n".join(blocks), ())


def _lessons(arm: str, candidates: Iterable[Candidate]) -> ArmContext:
    chosen = list(candidates)
    text = "\n".join(f"Lesson {c.lesson.lesson_id}: {c.lesson.text}" for c in chosen)
    return ArmContext(arm, text, tuple(c.lesson.lesson_id for c in chosen))


def free_lessons(candidates: Sequence[Candidate]) -> ArmContext:
    return _lessons("free_lessons", candidates)


def earned_ids(rows: Iterable[DecisionRow]) -> Set[str]:
    passed = {(r.lesson_id, r.step) for r in rows if r.lesson_id and r.result == "pass"
              and (r.step != "approval" or r.reason_code == "HUMAN_APPROVED")}
    ids = {lid for lid, _ in passed}
    return {lid for lid in ids if all((lid, s) in passed for s in ("poison", "replay", "approval"))}


def earned_lessons(candidates: Sequence[Candidate], rows: Iterable[DecisionRow]) -> ArmContext:
    ids = earned_ids(rows)
    return _lessons("earned_lessons", (c for c in candidates if c.lesson.lesson_id in ids))
