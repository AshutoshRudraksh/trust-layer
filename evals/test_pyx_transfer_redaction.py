"""Ticket 4: held out prompts never reach the run record.

The repo is public and the held out paper and rubric must stay out of it, so every call the transfer run
logs (worker and judges alike) stores prompt_sha256 and the replay key, never the prompt text. Keyless
replay matches by key, so it still reproduces the verdicts. redact_calls brings an already written log to
the same shape. Every test here is offline.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from evals.test_pyx_transfer_run import KEYS, PAPER, _setup
from pyx.transfer_run import RefuseToStart, redact_calls, run_transfer


def _lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_every_logged_call_of_a_live_run_is_hash_only(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    out = tmp_path / "run"
    run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    lines = _lines(out / "calls.jsonl")
    assert {l["kind"] for l in lines} == {"worker", "judge"}
    assert all(l["prompt"] is None and l["held_out"] is True for l in lines)
    worker_hashes = [l["prompt_sha256"] for l in lines if l["kind"] == "worker"]
    assert worker_hashes == [hashlib.sha256(p.encode("utf-8")).hexdigest() for p in live["worker"].prompts]
    assert PAPER not in (out / "calls.jsonl").read_text(encoding="utf-8")


def _unredacted_log(tmp_path):
    """A run whose log carries worker prompts in full, as the Nov 13 attempts wrote it."""
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    out = tmp_path / "run"
    run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    calls = out / "calls.jsonl"
    prompts = iter(live["worker"].prompts)
    rows = []
    for line in _lines(calls):
        if line["kind"] == "worker":
            line.update(prompt=next(prompts), held_out=False)
        rows.append(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")
    calls.write_text("".join(rows), encoding="utf-8")
    assert PAPER in calls.read_text(encoding="utf-8")
    return rubric, sha, paper, out


def test_redact_calls_drops_prompt_text_and_keeps_keyless_replay(tmp_path) -> None:
    rubric, sha, paper, out = _unredacted_log(tmp_path)
    before = _lines(out / "calls.jsonl")
    assert redact_calls(out / "calls.jsonl") == 10
    after = _lines(out / "calls.jsonl")
    assert PAPER not in (out / "calls.jsonl").read_text(encoding="utf-8")
    assert all(l["prompt"] is None and l["held_out"] is True for l in after)
    strip = lambda l: {k: v for k, v in l.items() if k not in ("prompt", "held_out")}
    assert [strip(l) for l in after] == [strip(l) for l in before]
    again = tmp_path / "replay"
    run_transfer(again, rubric, paper, None, None, env={}, src_log=out / "calls.jsonl", expected_sha256=sha)
    assert (again / "verdicts.tsv").read_bytes() == (out / "verdicts.tsv").read_bytes()


def test_redact_calls_is_idempotent(tmp_path) -> None:
    _, _, _, out = _unredacted_log(tmp_path)
    redact_calls(out / "calls.jsonl")
    first = (out / "calls.jsonl").read_bytes()
    assert redact_calls(out / "calls.jsonl") == 0
    assert (out / "calls.jsonl").read_bytes() == first


def test_redact_calls_refuses_a_prompt_that_does_not_match_its_hash(tmp_path) -> None:
    _, _, _, out = _unredacted_log(tmp_path)
    calls = out / "calls.jsonl"
    original = calls.read_bytes()
    calls.write_text(calls.read_text(encoding="utf-8").replace("Table 1 reports", "Table 9 reports", 1),
                     encoding="utf-8")
    tampered = calls.read_bytes()
    with pytest.raises(RefuseToStart, match="prompt_sha256"):
        redact_calls(calls)
    assert calls.read_bytes() == tampered != original
