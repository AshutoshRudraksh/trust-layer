"""Ticket 4, option A-strict (Ashutosh, Nov 13, 2026): the published call log carries no raw worker answer.

hash_worker_replies writes a copy of a call log in which every worker line's reply is replaced by its
reply_sha256. Judge lines (PASS or FAIL) and every other field stay byte for byte. The full log stays local.
Every test here is offline.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from evals.test_pyx_transfer_run import KEYS, _setup
from pyx.transfer_run import RefuseToStart, hash_worker_replies, run_transfer


def _lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").split("\n")[:-1]]


def _run(tmp_path):
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    out = tmp_path / "run"
    run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    return out / "calls.jsonl"


def test_worker_replies_become_hashes_and_nothing_else_changes(tmp_path) -> None:
    full = _run(tmp_path)
    public = tmp_path / "public.jsonl"
    assert hash_worker_replies(full, public) == 10
    before, after = _lines(full), _lines(public)
    assert len(before) == len(after)
    for b, a in zip(before, after):
        if b["kind"] == "worker":
            assert a["reply"] is None
            assert a["reply_sha256"] == hashlib.sha256(b["reply"].encode("utf-8")).hexdigest()
            assert {k: v for k, v in a.items() if k not in ("reply", "reply_sha256")} == \
                   {k: v for k, v in b.items() if k != "reply"}
        else:
            assert a == b
    text = public.read_text(encoding="utf-8")
    for b in before:
        if b["kind"] == "worker":
            assert b["reply"] not in text


def test_the_full_log_is_left_untouched(tmp_path) -> None:
    full = _run(tmp_path)
    original = full.read_bytes()
    hash_worker_replies(full, tmp_path / "public.jsonl")
    assert full.read_bytes() == original


def test_hashing_an_already_hashed_log_changes_nothing(tmp_path) -> None:
    full = _run(tmp_path)
    once, twice = tmp_path / "once.jsonl", tmp_path / "twice.jsonl"
    hash_worker_replies(full, once)
    assert hash_worker_replies(once, twice) == 0
    assert twice.read_bytes() == once.read_bytes()


def test_refuses_to_overwrite_its_source(tmp_path) -> None:
    full = _run(tmp_path)
    with pytest.raises(RefuseToStart, match="source"):
        hash_worker_replies(full, full)
