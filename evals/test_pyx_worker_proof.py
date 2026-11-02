"""PR G3 test: the committed live worker log replays keylessly to the committed answers, and grading
those answers keylessly reproduces the committed grade rows. Keys are removed and sockets blocked."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPLAY = ROOT / "evals" / "fixtures" / "pyx" / "replay"
sys.path.insert(0, str(ROOT / "scripts"))


def test_worker_proof_replays_keylessly_to_the_committed_answers_and_rows(tmp_path, monkeypatch) -> None:
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("the worker proof must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    from pyx_worker_proof import replay

    answers, tsv = tmp_path / "answers.jsonl", tmp_path / "decisions.tsv"
    faults = replay(REPLAY / "g3_worker.jsonl", answers, tsv)
    assert faults == []
    from pyx.decisions import DecisionLog
    rows = DecisionLog(tsv).read()
    assert [(r.task_id, r.copy) for r in rows] == [("T1", "clean"), ("T1", "planted"), ("T2", "clean")]
    assert answers.read_bytes() == (REPLAY / "g3_answers.jsonl").read_bytes()
    assert tsv.read_bytes() == (REPLAY / "g3_expected.tsv").read_bytes()
