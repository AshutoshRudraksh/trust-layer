"""PR D1c tests: RecordingClient logs every judge call attempt. Fake clients, no network."""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.meta_client import BudgetCapExceededError, EmptyReplyError
from pyx.call_log import CallLog, replay_key
from pyx.judges import judge_criterion
from pyx.recording import RecordingClient
from pyx.rubric import load_rubric


class _Reply:
    def __init__(self, text: str) -> None:
        self.output_text, self.input_tokens, self.output_tokens, self.cost_usd = text, 300, 40, 0.002


class _Fake:
    def __init__(self, script):
        self.script = list(script)

    def respond(self, prompt: str, **kw):
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Reply(item)

    chat = respond


def _criterion() -> dict:
    return next(c for c in load_rubric("T1", role="judge")["criteria"] if c["id"] == "T1.C8")


def test_records_each_attempt_including_a_malformed_retry(tmp_path: Path) -> None:
    log = CallLog(tmp_path / "r.jsonl", "r")
    a = RecordingClient(_Fake(["maybe", "PASS"]), log, judge="A", model="ma", endpoint="responses")
    b = RecordingClient(_Fake(["FAIL"]), log, judge="B", model="mb", endpoint="chat_completions")
    result = judge_criterion(_criterion(), "answer", a, b)
    lines = log.read()
    assert [(l["judge"], l["reply"]) for l in lines] == [("A", "maybe"), ("A", "PASS"), ("B", "FAIL")]
    assert result.judge_a.retries == 1
    first = lines[0]
    assert first["key"] == replay_key("A", "ma", "responses", first["prompt"], first["params"])
    assert first["params"]["temperature"] == 0 and first["params"]["max_output_tokens"] == 2048
    assert (first["input_tokens"], first["output_tokens"], first["cost_usd"]) == (300, 40, 0.002)
    assert first["latency_s"] >= 0


def test_records_a_judge_error_and_reraises_it(tmp_path: Path) -> None:
    log = CallLog(tmp_path / "r.jsonl", "r")
    a = RecordingClient(_Fake([EmptyReplyError("no final text")]), log, judge="A", model="ma", endpoint="responses")
    with pytest.raises(EmptyReplyError):
        a.respond("p", temperature=0)
    line = log.read()[0]
    assert line["outcome"] == "error" and line["error"] == "EmptyReplyError: no final text"
    assert line["reply"] == ""


def test_budget_stop_is_not_logged_as_a_call(tmp_path: Path) -> None:
    log = CallLog(tmp_path / "r.jsonl", "r")
    a = RecordingClient(_Fake([BudgetCapExceededError("stop")]), log, judge="A", model="ma", endpoint="responses")
    with pytest.raises(BudgetCapExceededError):
        a.respond("p")
    assert log.read() == []


def test_held_out_flag_reaches_the_log_and_attributes_pass_through(tmp_path: Path) -> None:
    log = CallLog(tmp_path / "r.jsonl", "r")
    inner = _Fake(["PASS"])
    inner.ledger = "the ledger"
    a = RecordingClient(inner, log, judge="A", model="ma", endpoint="responses", held_out=True)
    a.respond("hidden criterion")
    assert log.read()[0]["prompt"] is None
    assert a.ledger == "the ledger"
