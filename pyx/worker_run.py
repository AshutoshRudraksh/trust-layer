"""Run the worker live with recording or keyless from the call log, and store answers (plan G, PR G2).

One answer per (run_id, seed, arm, task_id, copy). The store is append only
JSONL: an identical repeat is skipped and a different answer under the same key
is refused, and a task already answered in the store makes no call on a rerun.
An empty reply gets one retry, then no answer and a recorded fault; a budget
stop is never caught. Live calls are recorded with kind "worker" and role
letter W; the keyless path serves them with no key and no network and fails on
a miss or an unserved line. This module builds no TraceCollector.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

from agents.http_retry import RateLimitedError
from agents.meta_client import EmptyReplyError
from pyx.call_log import CallLog, TornLogError, _canonical
from pyx.distill import trace_id
from pyx.grade_run import ReplayMismatchError
from pyx.recording import RecordingClient
from pyx.replay_client import ReplayClient
from pyx.worker import WORKER_MODEL, Answer, build_worker_prompt, parse_answer

WORKER_PARAMS = {"role": "research", "model": WORKER_MODEL, "reasoning_effort": "low",
                 "max_output_tokens": 2048, "temperature": 0}
Tasks = Sequence[Tuple[str, str]]  # (task_id, copy)


class AnswerConflictError(ValueError):
    """A different answer is already stored under the same run, seed, arm, task and copy."""


def _key(a: Answer) -> Tuple:
    return (a.run_id, a.seed, a.arm, a.task_id, a.copy)


class AnswerStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def read(self) -> List[Answer]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").split("\n")
        if lines[-1] != "":
            raise TornLogError(f"{self.path}: line {len(lines)} has no newline (torn write)")
        return [Answer(**dict(d, lesson_ids=tuple(d["lesson_ids"]))) for d in map(json.loads, lines[:-1])]

    def find(self, key: Tuple) -> Optional[Answer]:
        return next((a for a in self.read() if _key(a) == key), None)

    def append(self, answer: Answer) -> bool:
        old = self.find(_key(answer))
        if old is not None:
            if old == answer:
                return False
            raise AnswerConflictError(f"conflict: {_key(answer)} is already stored with other fields")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(asdict(answer)) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True


def _ask(prompt: str, client: Any) -> Tuple[Optional[str], str]:
    for _ in range(2):  # the first try plus one retry for an empty reply
        try:
            text = parse_answer(client.respond(prompt, **WORKER_PARAMS).output_text)
        except EmptyReplyError:
            text = None
        except RateLimitedError as exc:
            return None, f"{type(exc).__name__}: {exc}"
        if text is not None:
            return text, ""
    return None, "EMPTY after one retry"


def work(tasks: Tasks, run_id: str, seed: int, arm: str, client: Any, store: AnswerStore,
         context: str = "", lesson_ids: Tuple[str, ...] = ()) -> Tuple[List[Answer], List[str]]:
    answers, faults = [], []
    for task_id, copy in tasks:
        done = store.find((run_id, seed, arm, task_id, copy))
        if done is not None:
            answers.append(done)
            continue
        text, fault = _ask(build_worker_prompt(task_id, copy, context), client)
        if text is None:
            faults.append(f"{task_id} {copy}: {fault}")
            continue
        answer = Answer(run_id, seed, arm, task_id, copy, text, trace_id(run_id, task_id, text),
                        WORKER_MODEL, tuple(lesson_ids))
        store.append(answer)
        answers.append(answer)
    return answers, faults


def work_live(tasks: Tasks, run_id: str, seed: int, arm: str, log_path: Union[str, Path],
              store_path: Union[str, Path], meta: Optional[Any] = None, **kw: Any):
    if meta is None:
        from agents.meta_client import MetaModelClient
        meta = MetaModelClient()
    client = RecordingClient(meta, CallLog(log_path, run_id), judge="W", model=WORKER_MODEL,
                             endpoint="responses", kind="worker")
    return work(tasks, run_id, seed, arm, client, AnswerStore(store_path), **kw)


def work_keyless(tasks: Tasks, run_id: str, seed: int, arm: str, log_path: Union[str, Path],
                 store_path: Union[str, Path], **kw: Any):
    """No key, no network: serves every worker call from the log; a miss or an unserved line fails."""
    client = ReplayClient(CallLog(log_path, run_id).read(), judge="W", kind="worker")
    result = work(tasks, run_id, seed, arm, client, AnswerStore(store_path), **kw)
    if client.unused():
        raise ReplayMismatchError(f"unused worker log lines after replay: seq {[l['seq'] for l in client.unused()]}")
    return result


def answers_for_grading(store: AnswerStore, run_id: str) -> List[Tuple[str, str]]:
    return [(a.task_id, a.answer_text) for a in store.read() if a.run_id == run_id]
