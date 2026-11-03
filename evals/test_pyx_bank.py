"""H10: the earned lessons bank (pyx/bank.py) and the MCP tool surface.

The bank must reuse the pipeline's own definition of earned (pyx.arms
.earned_ids) and serve committed records verbatim. Fixtures build a
synthetic run directory the same way phase 1 writes one: candidates
jsonl files plus decisions.tsv, through the existing writers.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyx.bank import BankError, LessonBank
from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import Candidate, CandidateStore, Lesson, Provenance, make_lesson_id

REPO = Path(__file__).resolve().parents[1]
PILOT_DIR = REPO / "runs" / "pilot_thin_20261102_r1"


def _candidate(criterion: str, text: str, kind: str = "clean") -> Candidate:
    lesson = Lesson(lesson_id=make_lesson_id(criterion, text), text=text, scope="paper_anatomy",
                    created_from_trace_id="t" * 64, fixes_criterion_id=criterion,
                    status="candidate", version=1)
    provenance = Provenance(lesson_id=lesson.lesson_id, source_trace_id="t" * 64,
                            source_paper_id=criterion.split(".")[0], source_kind="document_text",
                            distiller_model="muse-spark-1.3-contributor",
                            text_sha256=__import__("hashlib").sha256(text.encode()).hexdigest())
    return Candidate(lesson, provenance)


def _row(lesson_id: str, step: str, result: str, reason: str = "", task: str = "T1") -> DecisionRow:
    return DecisionRow(lesson_id, step, result, reason, "", "", "", "", "0", "run_x", "", task, "clean")


def _run_dir(tmp_path: Path, candidates, rows) -> Path:
    run = tmp_path / "run_x"
    run.mkdir()
    store = CandidateStore(run / "candidates_r0_clean.jsonl")
    for c in candidates:
        store.append(c)
    DecisionLog(run / "decisions.tsv").append(rows)
    return run


EARNED_TEXT = "Define what diagnostic columns measure and summarize the authors' explanation."
FAILED_TEXT = "Transcribe every cell verbatim and never summarize anything."


def _earned_rows(lid: str):
    return [_row(lid, "poison", "pass"), _row(lid, "replay", "pass"),
            _row(lid, "approval", "pass", "HUMAN_APPROVED")]


def test_bank_serves_only_earned_lessons(tmp_path: Path) -> None:
    earned = _candidate("T1.C8", EARNED_TEXT)
    failed = _candidate("T2.C1", FAILED_TEXT)
    rows = _earned_rows(earned.lesson.lesson_id) + [
        _row(failed.lesson.lesson_id, "poison", "pass", task="T2"),
        _row(failed.lesson.lesson_id, "replay", "fail", "REGRESSION", task="T2")]
    bank = LessonBank.load(_run_dir(tmp_path, [earned, failed], rows))
    got = bank.earned_lessons()
    assert [g["lesson_id"] for g in got] == [earned.lesson.lesson_id]
    assert got[0]["text"] == EARNED_TEXT
    assert got[0]["fixes_criterion_id"] == "T1.C8"
    assert got[0]["task_id"] == "T1"


def test_bank_filters_by_task_and_criterion(tmp_path: Path) -> None:
    earned = _candidate("T1.C8", EARNED_TEXT)
    bank = LessonBank.load(_run_dir(tmp_path, [earned], _earned_rows(earned.lesson.lesson_id)))
    assert len(bank.earned_lessons(task_id="T1")) == 1
    assert bank.earned_lessons(task_id="T2") == []
    assert len(bank.earned_lessons(criterion_id="T1.C8")) == 1
    assert bank.earned_lessons(criterion_id="T1.C1") == []


def test_bank_provenance_for_earned_and_failed(tmp_path: Path) -> None:
    earned = _candidate("T1.C8", EARNED_TEXT)
    failed = _candidate("T2.C1", FAILED_TEXT)
    rows = _earned_rows(earned.lesson.lesson_id) + [
        _row(failed.lesson.lesson_id, "poison", "pass", task="T2"),
        _row(failed.lesson.lesson_id, "replay", "fail", "NO_FIX", task="T2")]
    bank = LessonBank.load(_run_dir(tmp_path, [earned, failed], rows))
    prov = bank.provenance(earned.lesson.lesson_id)
    assert prov["earned"] is True
    assert prov["provenance"]["distiller_model"] == "muse-spark-1.3-contributor"
    assert [d["step"] for d in prov["decisions"]] == ["poison", "replay", "approval"]
    failed_prov = bank.provenance(failed.lesson.lesson_id)
    assert failed_prov["earned"] is False
    assert failed_prov["decisions"][-1]["reason_code"] == "NO_FIX"
    with pytest.raises(BankError):
        bank.provenance("L_T9.C9_nope0000")


def test_bank_refuses_directories_that_are_not_runs(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BankError):
        LessonBank.load(empty)
    no_candidates = tmp_path / "no_candidates"
    no_candidates.mkdir()
    DecisionLog(no_candidates / "decisions.tsv").append(
        [_row("L_T1.C1_00000000", "poison", "pass")])
    with pytest.raises(BankError):
        LessonBank.load(no_candidates)


def test_bank_loads_the_committed_pilot_record() -> None:
    bank = LessonBank.load(PILOT_DIR)
    assert bank.earned_lessons() == []
    prov = bank.provenance("L_T1.C1_dfa7b126")
    assert prov["earned"] is False
    assert any(d["step"] == "replay" and d["result"] == "fail" for d in prov["decisions"])


def test_mcp_server_registers_exactly_two_tools() -> None:
    pytest.importorskip("mcp")
    from pyx.mcp_server import build_server
    import asyncio
    bank = LessonBank.load(PILOT_DIR)
    server = build_server(bank)
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == ["get_lesson_provenance", "query_earned_lessons"]
