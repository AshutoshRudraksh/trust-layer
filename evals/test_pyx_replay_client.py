"""PR D3a tests: ReplayClient serves judge replies from the call log. No keys, no network."""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

from agents.http_retry import RateLimitedError
from agents.meta_client import EmptyReplyError
from pyx import replay_client
from pyx.call_log import CallLog
from pyx.recording import RecordingClient
from pyx.replay_client import ReplayClient, ReplayMissError

PARAMS = {"temperature": 0, "max_output_tokens": 2048}


@pytest.fixture(autouse=True)
def no_keys_no_network(monkeypatch):
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("replay must not open network connections")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class _Reply:
    def __init__(self, text: str) -> None:
        self.output_text, self.input_tokens, self.output_tokens, self.cost_usd = text, 300, 40, 0.002


class _Fake:
    def __init__(self, script):
        self.script = list(script)

    def respond(self, prompt, **kw):
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Reply(item)


def _record(tmp_path: Path, script, prompts) -> list:
    log = CallLog(tmp_path / "r.jsonl", "r")
    rec = RecordingClient(_Fake(script), log, judge="A", model="ma", endpoint="responses")
    for p in prompts:
        try:
            rec.respond(p, **PARAMS)
        except (EmptyReplyError, RateLimitedError):
            pass
    return log.read()


def test_serves_the_logged_reply_tokens_and_cost(tmp_path: Path) -> None:
    client = ReplayClient(_record(tmp_path, ["PASS"], ["p1"]), judge="A")
    resp = client.respond("p1", **PARAMS)
    assert (resp.output_text, resp.input_tokens, resp.output_tokens, resp.cost_usd) == ("PASS", 300, 40, 0.002)


def test_same_key_lines_are_served_in_recorded_order(tmp_path: Path) -> None:
    client = ReplayClient(_record(tmp_path, ["maybe", "PASS"], ["p1", "p1"]), judge="A")
    assert [client.respond("p1", **PARAMS).output_text for _ in range(2)] == ["maybe", "PASS"]


@pytest.mark.parametrize("exc", [EmptyReplyError("no final text"), RateLimitedError("HTTP 429 from x")])
def test_error_lines_reraise_the_same_class_and_message(tmp_path: Path, exc: Exception) -> None:
    client = ReplayClient(_record(tmp_path, [exc], ["p1"]), judge="A")
    with pytest.raises(type(exc), match=str(exc)):
        client.respond("p1", **PARAMS)


@pytest.mark.parametrize("prompt,params", [("p2", PARAMS), ("p1", {**PARAMS, "temperature": 1})])
def test_a_changed_prompt_or_param_misses_loudly(tmp_path: Path, prompt: str, params: dict) -> None:
    client = ReplayClient(_record(tmp_path, ["PASS"], ["p1"]), judge="A")
    with pytest.raises(ReplayMissError) as info:
        client.respond(prompt, **params)
    msg = str(info.value)
    assert "judge A" in msg and "model ma" in msg and "key " in msg and "prompt_sha256 " in msg


def test_serving_past_the_recorded_lines_misses(tmp_path: Path) -> None:
    client = ReplayClient(_record(tmp_path, ["PASS"], ["p1"]), judge="A")
    client.respond("p1", **PARAMS)
    with pytest.raises(ReplayMissError):
        client.respond("p1", **PARAMS)


def test_unused_lists_lines_never_served(tmp_path: Path) -> None:
    lines = _record(tmp_path, ["PASS", "FAIL"], ["p1", "p2"])
    client = ReplayClient(lines, judge="A")
    client.respond("p1", **PARAMS)
    assert [l["seq"] for l in client.unused()] == [1]


def test_other_judges_lines_are_ignored_and_no_client_class_is_imported(tmp_path: Path) -> None:
    client = ReplayClient(_record(tmp_path, ["PASS"], ["p1"]), judge="B")
    assert client.unused() == []
    assert not hasattr(replay_client, "MetaModelClient") and not hasattr(replay_client, "BasetenClient")
