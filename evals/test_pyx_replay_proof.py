"""PR D3c test: the committed live proof log replays keylessly to the committed decisions rows.

Anyone cloning the repo can run this with no API key: keys are removed and sockets blocked.
"""
from __future__ import annotations

import socket
from pathlib import Path

from pyx.decisions import DecisionLog, rows_from_grade
from pyx.grade_run import grade_keyless

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"
PROOF = FIX / "replay" / "d3_proof.jsonl"
EXPECTED = FIX / "replay" / "d3_proof_expected.tsv"
ANSWERS = [(f[:2], (FIX / f"{f}.md").read_text()) for f in ("T1_good", "T1_bad", "T2_good", "T2_bad")]


def test_committed_proof_replays_keylessly_to_the_committed_rows(monkeypatch) -> None:
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("the keyless proof must not open network connections")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    reports = grade_keyless(ANSWERS, PROOF)
    rows = [row for r in reports for row in rows_from_grade(r, run_id="d3_proof", seed=0)]
    assert rows == DecisionLog(EXPECTED).read()
