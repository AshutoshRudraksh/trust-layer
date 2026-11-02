"""PR H6 tests: the terminal entry `python -m pyx.run` (plan H6 tests 1 to 9). Temp files and StringIO only."""
from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
from io import StringIO
from pathlib import Path

import pytest

from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import CandidateStore
from pyx.run import main

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx" / "replay" / "e4_distill_candidates.jsonl"
CANDS = CandidateStore(FIX).read()
A, B, C = CANDS[0], CANDS[1], CANDS[2]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def _setup(tmp, status="FROZEN"):
    ev = tmp / "EVAL.md"
    ev.write_text(f"# EVAL\nStatus: {status}\n")
    rows = [DecisionRow(c.lesson.lesson_id, s, "pass", "", "T1.C1" if s == "replay" else "", "", "", "", "0", "r1",
                        "", "T1", "clean") for c in (A, B) for s in ("poison", "replay")]
    rows.append(DecisionRow(C.lesson.lesson_id, "poison", "pass", "", "", "", "", "", "0", "r1", "", "T1", "clean"))
    DecisionLog(tmp / "d.tsv").append(rows)
    return ev, hashlib.sha256(ev.read_bytes()).hexdigest()


def _approve(tmp, typed, sha=None, cands=FIX, dec="d.tsv"):
    ev, h = _setup(tmp) if not (tmp / "EVAL.md").exists() else (tmp / "EVAL.md", None)
    h = sha or h or hashlib.sha256(ev.read_bytes()).hexdigest()
    out = StringIO()
    code = main(["approve", "--candidates", str(cands), "--decisions", str(tmp / dec), "--gate-db",
                 str(tmp / "g.sqlite"), "--eval", str(ev), "--eval-sha256", h, "--run-id", "r1"],
                StringIO(typed), out)
    return code, out.getvalue()


def _approvals(tmp, dec="d.tsv"):
    return [(r.lesson_id, r.reason_code) for r in DecisionLog(tmp / dec).read() if r.step == "approval"]


def test_approve_shows_exact_text_and_hash_for_admissible_lessons_only(tmp_path) -> None:
    code, out = _approve(tmp_path, "")
    assert code == 0
    for c in (A, B):
        assert c.lesson.text in out and c.provenance.text_sha256 in out
    assert C.lesson.text not in out


def test_typed_approve_and_deny_in_any_case_write_one_row_each(tmp_path) -> None:
    code, _ = _approve(tmp_path, "  APPROVE \nDeny\n")
    assert code == 0
    assert _approvals(tmp_path) == [(A.lesson.lesson_id, "HUMAN_APPROVED"), (B.lesson.lesson_id, "HUMAN_DENIED")]


@pytest.mark.parametrize("typed", ["", "\n\n", "yes\nno\n", "APPROVED\nDENIED\n", "approv\n"])
def test_empty_or_other_input_writes_nothing(tmp_path, typed) -> None:
    code, out = _approve(tmp_path, typed)
    assert code == 0 and _approvals(tmp_path) == [] and "skipped" in out
    with sqlite3.connect(tmp_path / "g.sqlite") as db:
        assert db.execute("select count(*) from approvals").fetchone()[0] == 0


def test_gate_record_is_bound_to_lesson_id_and_text_hash(tmp_path) -> None:
    _approve(tmp_path, "approve\n\n")
    with sqlite3.connect(tmp_path / "g.sqlite") as db:
        target, payload, ins = db.execute("select target, payload_json, instruction_id from actions").fetchone()
    assert target == A.lesson.lesson_id and json.loads(payload)["text_sha256"] == A.provenance.text_sha256
    assert ins == f"approve_{A.lesson.lesson_id}_{A.provenance.text_sha256[:8]}"


def test_a_changed_text_is_refused_and_writes_nothing(tmp_path) -> None:
    lines = FIX.read_text().splitlines()
    first = json.loads(lines[0])
    first["lesson"]["text"] += " Also round freely."
    edited = tmp_path / "c.jsonl"
    edited.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
    code, _ = _approve(tmp_path, "approve\napprove\n", cands=edited)
    assert code == 3 and _approvals(tmp_path) == []


def test_a_denied_lesson_stays_locked_and_rerun_skips_decided_lessons(tmp_path) -> None:
    _approve(tmp_path, "deny\n\n")
    code, out = _approve(tmp_path, "\n")
    assert code == 0 and A.lesson.text not in out and _approvals(tmp_path) == [(A.lesson.lesson_id, "HUMAN_DENIED")]
    (tmp_path / "e.tsv").write_text((tmp_path / "d.tsv").read_text().rsplit("\n", 2)[0] + "\n")
    code, out = _approve(tmp_path, "approve\n\n", dec="e.tsv")
    assert "locked" in out and _approvals(tmp_path, "e.tsv") == []


@pytest.mark.parametrize("status,bad_hash", [("DRAFT", False), ("FROZEN", True)])
def test_approve_refuses_before_showing_anything_unless_eval_is_frozen(tmp_path, status, bad_hash) -> None:
    _setup(tmp_path, status)
    code, out = _approve(tmp_path, "approve\napprove\n", sha="0" * 64 if bad_hash else None)
    assert code == 2 and A.lesson.text not in out and _approvals(tmp_path) == []


def test_check_eval_exit_codes(tmp_path) -> None:
    ev, h = _setup(tmp_path)
    out = StringIO()
    assert main(["check-eval", "--eval", str(ev), "--eval-sha256", h], StringIO(), out) == 0 and h in out.getvalue()
    assert main(["check-eval", "--eval", str(ev), "--eval-sha256", "0" * 64], StringIO(), StringIO()) == 2


def test_cli_imports_no_http_client_and_no_tracing() -> None:
    src = (Path(__file__).resolve().parent.parent / "pyx" / "run.py").read_text()
    for name in ("agents.tracing", "httpx", "requests", "urllib"):
        assert name not in src
