"""PR D1b tests: the call log. No network, no real keys (fake values set in env)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyx.call_log import CallLog, KeyLeakError, TornLogError, replay_key
from pyx.checker import check_answer
from pyx.rubric import load_rubric

FAKE = "fake-live-key-value-0123456789"
PARAMS = {"temperature": 0, "max_output_tokens": 2048, "reasoning_effort": "low"}
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pyx"


def _judge(log: CallLog, prompt: str = "grade this", reply: str = "PASS", **kw) -> dict:
    return log.append_judge(judge="A", model="m", endpoint="responses", params=PARAMS, prompt=prompt,
                            reply=reply, outcome="ok", input_tokens=10, output_tokens=5,
                            reasoning_tokens=3, cost_usd=0.001, latency_s=1.5, **kw)


def test_replay_key_is_stable_and_changes_with_every_input() -> None:
    base = replay_key("A", "m", "responses", "p", PARAMS)
    assert base == replay_key("A", "m", "responses", "p", dict(reversed(list(PARAMS.items()))))
    assert len({base, replay_key("B", "m", "responses", "p", PARAMS), replay_key("A", "m2", "responses", "p", PARAMS),
                replay_key("A", "m", "chat", "p", PARAMS), replay_key("A", "m", "responses", "q", PARAMS),
                replay_key("A", "m", "responses", "p", {**PARAMS, "temperature": 1})}) == 6


def test_judge_line_has_the_fixed_fields_and_survives_a_reopen(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    entry = _judge(CallLog(path, "run1"))
    _judge(CallLog(path, "run1"), reply="FAIL")
    lines = CallLog(path, "run1").read()
    assert [l["seq"] for l in lines] == [0, 1]
    assert entry["key"] == replay_key("A", "m", "responses", "grade this", PARAMS)
    assert set(entry) == {"run_id", "seq", "kind", "judge", "model", "endpoint", "params", "key", "prompt_sha256",
                          "prompt", "held_out", "reply", "outcome", "error", "input_tokens", "output_tokens",
                          "reasoning_tokens", "cost_usd", "latency_s"}
    assert path.read_text().endswith("\n")


def test_held_out_keeps_only_the_prompt_hash(tmp_path: Path) -> None:
    entry = _judge(CallLog(tmp_path / "r.jsonl", "r"), prompt="secret criterion text", held_out=True)
    assert entry["prompt"] is None and len(entry["prompt_sha256"]) == 64
    assert "secret criterion text" not in (tmp_path / "r.jsonl").read_text()


def test_torn_last_line_is_reported_and_blocks_appends(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    _judge(CallLog(path, "r"))
    with path.open("a") as fh:
        fh.write('{"run_id": "r", "seq": 1, "ki')
    with pytest.raises(TornLogError, match="line 2"):
        CallLog(path, "r").read()
    with pytest.raises(TornLogError):
        _judge(CallLog(path, "r"))


@pytest.mark.parametrize("env_name", ["MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"])
def test_live_key_values_are_refused(tmp_path: Path, monkeypatch, env_name: str) -> None:
    monkeypatch.setenv(env_name, FAKE)
    path = tmp_path / "r.jsonl"
    _judge(CallLog(path, "r"))
    before = path.read_text()
    with pytest.raises(KeyLeakError) as info:
        _judge(CallLog(path, "r"), reply=f"leaked {FAKE}")
    assert FAKE not in str(info.value)
    assert path.read_text() == before


@pytest.mark.parametrize("text", ["sk-abcdefghijklmnopqrstu", "Bearer abcdefghijklmnopqrstuvwx",
                                  "ghp_abcdefghijklmnopqrstuv", "AKIAABCDEFGHIJKLMNOP", "-----BEGIN PRIVATE KEY"])
def test_key_shaped_patterns_are_refused(tmp_path: Path, text: str) -> None:
    with pytest.raises(KeyLeakError):
        _judge(CallLog(tmp_path / "r.jsonl", "r"), reply=text)
    assert not (tmp_path / "r.jsonl").exists() or (tmp_path / "r.jsonl").read_text() == ""


def test_checker_line_holds_hashes_and_every_programmatic_verdict(tmp_path: Path) -> None:
    rubric = load_rubric("T1", role="checker")
    answer = (FIXTURES / "T1_bad.md").read_text()
    verdicts = check_answer(answer, rubric)
    entry = CallLog(tmp_path / "r.jsonl", "r").append_checker("T1", answer, rubric, verdicts)
    assert entry["kind"] == "checker" and entry["cost_usd"] == 0
    assert all(len(entry[k]) == 64 for k in ("answer_sha256", "rubric_sha256", "checker_sha256"))
    assert [v["criterion_id"] for v in entry["verdicts"]] == [v.criterion_id for v in verdicts]
    assert entry["verdicts"][0]["status"] == "FAIL"
    assert json.loads((tmp_path / "r.jsonl").read_text())["verdicts"][0]["evidence"]
