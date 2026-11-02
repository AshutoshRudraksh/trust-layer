"""PR G2 tests: answer store, live and keyless worker runs, handoff to grading (plan G tests 8 to 12a)."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from agents.meta_client import BudgetCapExceededError, EmptyReplyError
from pyx.distill import trace_id
from pyx.replay_client import ReplayMissError
from pyx.grade_run import ReplayMismatchError
from pyx.worker import WORKER_MODEL, Answer
from pyx.worker_run import (WORKER_PARAMS, AnswerConflictError, AnswerStore, answers_for_grading, work_keyless,
                            work_live)

ROOT = Path(__file__).resolve().parent.parent
TASKS = [("T1", "clean"), ("T2", "clean")]


@dataclass
class Reply:
    output_text: str
    input_tokens: int = 10
    output_tokens: int = 5
    cost_usd: float = 0.0
    model: str = WORKER_MODEL


class Fake:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def respond(self, prompt, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return Reply(r)


def _live(tmp_path, client, tasks=TASKS[:1], **kw):
    return work_live(tasks, "r1", 0, "no_memory", tmp_path / "log.jsonl", tmp_path / "answers.jsonl",
                     meta=client, **kw)


def test_one_call_with_the_plan_settings_and_one_stored_answer(tmp_path) -> None:
    fake = Fake(["## Architecture\nActor"])
    answers, faults = _live(tmp_path, fake, lesson_ids=("L_a",), context="Lesson: a")
    assert faults == [] and len(fake.calls) == 1
    assert fake.calls[0] == WORKER_PARAMS
    assert (WORKER_PARAMS["temperature"], WORKER_PARAMS["reasoning_effort"], WORKER_PARAMS["max_output_tokens"],
            WORKER_PARAMS["model"]) == (0, "low", 6144, WORKER_MODEL)
    a = answers[0]
    assert a.trace_id == trace_id("r1", "T1", a.answer_text) and a.lesson_ids == ("L_a",)
    assert AnswerStore(tmp_path / "answers.jsonl").read() == answers


def test_rerun_makes_no_call_and_a_conflicting_answer_raises(tmp_path) -> None:
    _live(tmp_path, Fake(["first"]))
    fake = Fake([])
    again, _ = _live(tmp_path, fake)
    assert fake.calls == [] and len(AnswerStore(tmp_path / "answers.jsonl").read()) == 1 and again[0].answer_text == "first"
    other = Answer("r1", 0, "no_memory", "T1", "clean", "second", "t", WORKER_MODEL, ())
    with pytest.raises(AnswerConflictError):
        AnswerStore(tmp_path / "answers.jsonl").append(other)


def test_keyless_serves_recorded_lines_and_fails_on_miss_or_unused(tmp_path, monkeypatch) -> None:
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    live, _ = _live(tmp_path, Fake(["a1", "a2"]), tasks=TASKS)
    replayed, faults = work_keyless(TASKS, "r1", 0, "no_memory", tmp_path / "log.jsonl", tmp_path / "k.jsonl")
    assert replayed == live and faults == []
    with pytest.raises(ReplayMissError):
        work_keyless([("T1", "planted")], "r1", 0, "no_memory", tmp_path / "log.jsonl", tmp_path / "k2.jsonl")
    with pytest.raises(ReplayMismatchError):
        work_keyless(TASKS[:1], "r1", 0, "no_memory", tmp_path / "log.jsonl", tmp_path / "k3.jsonl")


def test_empty_reply_retries_once_then_faults_and_budget_stop_propagates(tmp_path) -> None:
    fake = Fake(["", EmptyReplyError("no text")])
    answers, faults = _live(tmp_path, fake)
    assert answers == [] and len(fake.calls) == 2 and faults and "T1" in faults[0]
    assert AnswerStore(tmp_path / "answers.jsonl").read() == []
    ok, _ = _live(tmp_path, Fake(["", "second try"]))
    assert ok[0].answer_text == "second try"
    with pytest.raises(BudgetCapExceededError):
        work_live(TASKS[1:], "r1", 0, "no_memory", tmp_path / "l.jsonl", tmp_path / "a.jsonl",
                  meta=Fake([BudgetCapExceededError("cap")]))


def test_answers_for_grading_gives_task_and_text_in_store_order(tmp_path) -> None:
    _live(tmp_path, Fake(["a1", "a2"]), tasks=TASKS)
    assert answers_for_grading(AnswerStore(tmp_path / "answers.jsonl"), "r1") == [("T1", "a1"), ("T2", "a2")]
    assert answers_for_grading(AnswerStore(tmp_path / "answers.jsonl"), "other") == []


def test_worker_runs_open_no_connection_and_build_no_trace_collector(tmp_path) -> None:
    code = f"""
import socket, sys
def refuse(*a, **k): raise AssertionError("network")
socket.socket.connect = socket.socket.connect_ex = refuse
socket.create_connection = refuse
import agents.tracing as t
def no_tracer(*a, **k): raise AssertionError("TraceCollector built")
t.TraceCollector.__init__ = no_tracer
sys.path.insert(0, {str(ROOT / 'evals')!r})
from test_pyx_worker_run import Fake
from pyx.worker_run import work_live, work_keyless
from pathlib import Path
d = Path({str(tmp_path)!r})
live, _ = work_live([("T1", "clean")], "r1", 0, "no_memory", d / "log.jsonl", d / "a.jsonl", meta=Fake(["x"]))
again, _ = work_keyless([("T1", "clean")], "r1", 0, "no_memory", d / "log.jsonl", d / "k.jsonl")
assert live == again
print("ok")
"""
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "ok", out.stderr
    assert "agents.tracing" not in (ROOT / "pyx" / "worker_run.py").read_text()


def test_live_default_client_is_the_worker_client(tmp_path, monkeypatch) -> None:
    import pyx.worker_run as worker_run
    fake = Fake(["answer"])
    monkeypatch.setattr(worker_run, "worker_client", lambda: fake)
    work_live(TASKS[:1], "r1", 0, "no_memory", tmp_path / "log.jsonl", tmp_path / "answers.jsonl")
    assert len(fake.calls) == 1
