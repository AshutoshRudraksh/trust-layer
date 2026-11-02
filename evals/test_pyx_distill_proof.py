"""PR E4 test: the committed live distill log replays keylessly to the committed candidate lessons.

Anyone cloning the repo can run this with no API key: keys are removed and sockets blocked.
"""
from __future__ import annotations

import socket
from pathlib import Path

from pyx.distill import distill_keyless
from pyx.grade_run import grade_keyless
from pyx.lessons import CandidateStore

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"
REPLAY = FIX / "replay"
NAMES = ("T1_good", "T1_bad", "T2_good", "T2_bad")
ANSWERS = [(n[:2], (FIX / f"{n}.md").read_text()) for n in NAMES]


def test_committed_distill_proof_replays_keylessly_to_the_committed_candidates(monkeypatch) -> None:
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("the keyless proof must not open network connections")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    pairs = list(zip(grade_keyless(ANSWERS, REPLAY / "d3_proof.jsonl"), [a for _, a in ANSWERS]))
    candidates, faults = distill_keyless(pairs, "e4_proof", REPLAY / "e4_distill.jsonl")
    expected = CandidateStore(REPLAY / "e4_distill_candidates.jsonl")
    assert candidates == expected.read() and faults == []
    assert "".join(c.to_json() + "\n" for c in candidates) == expected.path.read_text(encoding="utf-8")
