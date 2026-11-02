"""PR F3 test: the $0 poison proof rerun gives the committed decisions rows byte for byte.

Keys are removed and sockets blocked, so any network use fails the test.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = ROOT / "evals" / "fixtures" / "pyx" / "poison" / "f3_expected.tsv"
sys.path.insert(0, str(ROOT / "scripts"))


def test_poison_proof_reproduces_the_committed_rows_with_no_network(tmp_path, monkeypatch) -> None:
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("the poison proof must not open network connections")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    from pyx_poison_proof import run_proof

    out = tmp_path / "decisions.tsv"
    verdicts, added_on_rerun = run_proof(out)
    assert len(verdicts) == 11 and added_on_rerun == 0
    assert out.read_text(encoding="utf-8") == EXPECTED.read_text(encoding="utf-8")
