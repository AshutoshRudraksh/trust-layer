"""Grade answers live with recording, or keyless from the recorded call log.

grade_live wraps the real judge clients in RecordingClient and writes one
checker line per answer before its judge lines. grade_keyless builds only
ReplayClients, so no key is read and no network is opened. For each answer it
reruns the checker and compares with the logged checker line: the checker
source hash stamp, the rubric hash, the answer hash and every programmatic
verdict must match, or ReplayMismatchError stops the run showing both values.
After the last answer, any recorded judge line that was never served also stops
the run, since the replay did not walk the path the live run walked.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

from agents.baseten_client import BASETEN_MODEL, BasetenClient
from agents.meta_client import MetaModelClient
from pyx.call_log import CHECKER_SOURCE, CallLog, _canonical, _sha256
from pyx.checker import check_answer
from pyx.judges import GradeReport, grade_answer
from pyx.recording import RecordingClient
from pyx.replay_client import ReplayClient, ReplayMissError
from pyx.rubric import load_rubric

META_MODEL = "muse-spark-1.3-contributor"
Answers = Sequence[Tuple[str, str]]  # (task_id, answer_text)


class ReplayMismatchError(RuntimeError):
    """The keyless rerun differs from the recorded run."""


def current_checker_sha256() -> str:
    return _sha256(CHECKER_SOURCE.read_bytes())


def grade_live(answers: Answers, run_id: str, log_path: Union[str, Path], meta: Optional[Any] = None,
               baseten: Optional[Any] = None) -> List[GradeReport]:
    log = CallLog(log_path, run_id)
    meta = meta if meta is not None else MetaModelClient()
    baseten = baseten if baseten is not None else BasetenClient()
    reports = []
    for task_id, text in answers:
        rubric = load_rubric(task_id, role="checker")
        held_out = rubric.get("split") != "training"
        log.append_checker(task_id, text, rubric, check_answer(text, rubric))
        a = RecordingClient(meta, log, judge="A", model=META_MODEL, endpoint="responses", held_out=held_out)
        b = RecordingClient(baseten, log, judge="B", model=BASETEN_MODEL, endpoint="chat_completions",
                            held_out=held_out)
        reports.append(grade_answer(text, task_id, a, b))
    return reports


def _check_against_log(task_id: str, text: str, logged: dict) -> None:
    rubric = load_rubric(task_id, role="checker")
    expected = {"task_id": task_id, "checker_sha256": current_checker_sha256(),
                "rubric_sha256": _sha256(_canonical(rubric)), "answer_sha256": _sha256(text)}
    for field, now in expected.items():
        if logged.get(field) != now:
            raise ReplayMismatchError(f"{task_id}: {field} differs: logged {logged.get(field)}, now {now}")
    rerun = json.loads(json.dumps([asdict(v) for v in check_answer(text, rubric)]))
    for old, new in zip(logged["verdicts"], rerun):
        if old != new:
            raise ReplayMismatchError(f"{task_id}: checker verdict for {new['criterion_id']} differs: "
                                      f"logged {old['status']}, now {new['status']}")
    if len(logged["verdicts"]) != len(rerun):
        raise ReplayMismatchError(f"{task_id}: logged {len(logged['verdicts'])} checker verdicts, now {len(rerun)}")


def grade_keyless(answers: Answers, log_path: Union[str, Path]) -> List[GradeReport]:
    lines = CallLog(log_path, "").read()
    checker_lines = [l for l in lines if l["kind"] == "checker"]
    a, b = ReplayClient(lines, judge="A"), ReplayClient(lines, judge="B")
    reports = []
    for i, (task_id, text) in enumerate(answers):
        if i >= len(checker_lines):
            raise ReplayMissError(f"no checker line logged for answer {i + 1} ({task_id})")
        _check_against_log(task_id, text, checker_lines[i])
        reports.append(grade_answer(text, task_id, a, b))
    unused = a.unused() + b.unused()
    if unused or len(checker_lines) > len(answers):
        raise ReplayMismatchError(f"unused log lines after replay: {len(unused)} judge lines "
                                  f"(seq {[l['seq'] for l in unused]}), "
                                  f"{len(checker_lines) - len(answers)} checker lines")
    return reports
