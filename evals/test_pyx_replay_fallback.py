"""PR H9h tests: the replay client falls back to the newest line for a key.

The counted run was interrupted mid stage 1; on resume the live engine
re-served a recorded worker reply for the next repetition's fresh cell, so
its log holds two executions of a prompt the rerun serves three times.
These tests pin the fallback: the over-serve returns the most recent
recorded reply for that identical key, a recorded error re-raises, and a
key with no line at all still stops the rerun. Fakes only; no network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pyx.call_log import CallLog
from pyx.replay_client import ReplayClient, ReplayMissError

PROMPT = "answer the task"


def _lines(tmp_path: Path, replies: list, outcome: str = "ok", error: str = "") -> list:
    log = CallLog(tmp_path / "calls.jsonl", "run_fallback")
    for reply in replies:
        log.append_judge(
            judge="W", model="m", endpoint="responses", params={}, prompt=PROMPT,
            reply=reply, outcome=outcome, input_tokens=10, output_tokens=3,
            reasoning_tokens=0, cost_usd=0.5, latency_s=1.0, error=error, kind="worker",
        )
    return log.read()


def test_an_over_serve_returns_the_most_recent_recorded_reply(tmp_path: Path) -> None:
    replay = ReplayClient(_lines(tmp_path, ["first", "second"]), judge="W", kind="worker", fallback=True)
    assert replay.respond(PROMPT).output_text == "first"
    assert replay.respond(PROMPT).output_text == "second"
    assert replay.respond(PROMPT).output_text == "second"


def test_an_over_serve_of_a_recorded_error_reraises_it(tmp_path: Path) -> None:
    replay = ReplayClient(
        _lines(tmp_path, [""], outcome="error", error="RuntimeError: boom"), judge="W", kind="worker", fallback=True
    )
    with pytest.raises(RuntimeError):
        replay.respond(PROMPT)
    with pytest.raises(RuntimeError):
        replay.respond(PROMPT)


def test_a_key_with_no_line_at_all_still_raises_a_miss(tmp_path: Path) -> None:
    replay = ReplayClient(_lines(tmp_path, ["only"]), judge="W", kind="worker")
    with pytest.raises(ReplayMissError):
        replay.respond("a prompt that was never recorded")
