"""Run the poison check over a candidate store and write one decisions.tsv row per candidate.

paper_text finds a paper's task id in the manifest table by its pinned arXiv id,
then reads pyx/tasks/<task id>_*.<copy>.md, where copy names the text the worker
read for that run (clean or planted). A paper in the manifest with no text in the
repo raises PaperTextMissingError; the run looks up every paper before checking
anything, so it stops before writing any row instead of passing a lesson it could
not check. The candidate store is only read, never rewritten.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Sequence

from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import CandidateStore
from pyx.poison import PoisonVerdict, check_candidate

TASKS = Path(__file__).resolve().parent / "tasks"
COPIES = frozenset({"clean", "planted"})
_ROW = re.compile(r"^\|\s*([TH]\d+)\s*\|[^|]*\|[^|]*\|\s*(\S+)\s*\|", re.M)


class UnknownPaperError(KeyError):
    """The paper id is not in the manifest."""


class PaperTextMissingError(FileNotFoundError):
    """The paper is in the manifest but its text is not in the repo."""


def paper_text(paper_id: str, copy: str) -> str:
    if copy not in COPIES:
        raise ValueError(f"copy {copy!r} is not one of {sorted(COPIES)}")
    tasks = dict((pid, tid) for tid, pid in _ROW.findall((TASKS / "manifest.md").read_text(encoding="utf-8")))
    if paper_id not in tasks:
        raise UnknownPaperError(paper_id)
    found = sorted(TASKS.glob(f"{tasks[paper_id]}_*.{copy}.md"))
    if len(found) != 1:
        raise PaperTextMissingError(f"{paper_id} ({tasks[paper_id]}): {len(found)} {copy} text files in pyx/tasks")
    return found[0].read_text(encoding="utf-8")


def poison_rows(verdicts: Sequence[PoisonVerdict], run_id: str, seed: int, copy: str = "") -> List[DecisionRow]:
    return [DecisionRow(lesson_id=v.lesson_id, step="poison", result="pass" if v.passed else "fail",
                        reason_code=v.reason_code, criteria_fixed="", criteria_broken="", judge_a="",
                        judge_b="", seed=str(seed), run_id=run_id, flags="", task_id="", copy=copy)
            for v in verdicts]


def run_poison(store: CandidateStore, run_id: str, seed: int, copy: str, log: DecisionLog) -> List[PoisonVerdict]:
    candidates = store.read()
    texts = {pid: paper_text(pid, copy) for pid in dict.fromkeys(c.provenance.source_paper_id for c in candidates)}
    verdicts = [check_candidate(c, texts[c.provenance.source_paper_id]) for c in candidates]
    log.append(poison_rows(verdicts, run_id, seed, copy))
    return verdicts
