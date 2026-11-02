"""PR F2 tests: paper text lookup from the manifest, poison rows for decisions.tsv, and the run over a store."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pyx.call_log import _sha256
from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import Candidate, CandidateStore, Lesson, Provenance, make_lesson_id
from pyx.poison import PoisonVerdict
from pyx.poison_run import PaperTextMissingError, UnknownPaperError, paper_text, poison_rows, run_poison

ROOT = Path(__file__).resolve().parent.parent
E4 = CandidateStore(ROOT / "evals" / "fixtures" / "pyx" / "replay" / "e4_distill_candidates.jsonl").read()
T1 = [c for c in E4 if c.provenance.source_paper_id == "2303.11366v4"]
T2 = [c for c in E4 if c.provenance.source_paper_id == "2407.01489v2"]
TEXT = "Name the table each number comes from."
LID = make_lesson_id("T1.C1", TEXT)
DOC = Candidate(Lesson(LID, TEXT, "paper_anatomy", "tr", "T1.C1", "candidate", 1),
                Provenance(LID, "tr", "2303.11366v4", "document_text", "m", _sha256(TEXT)))


def test_t1_paper_id_resolves_to_the_named_copy() -> None:
    tasks = ROOT / "pyx" / "tasks"
    assert paper_text("2303.11366v4", copy="clean") == (tasks / "T1_reflexion_v4.clean.md").read_text(encoding="utf-8")
    assert paper_text("2303.11366v4", copy="planted") == (tasks / "T1_reflexion_v4.planted.md").read_text(encoding="utf-8")


def test_a_manifest_paper_with_no_text_in_the_repo_raises() -> None:
    with pytest.raises(PaperTextMissingError, match="2407.01489v2"):
        paper_text("2407.01489v2", copy="clean")


def test_an_unknown_paper_id_raises() -> None:
    with pytest.raises(UnknownPaperError):
        paper_text("9999.00001v1", copy="clean")


def test_rows_for_a_fail_and_a_pass() -> None:
    rows = poison_rows([PoisonVerdict("L_a", False, "UNTRUSTED_SOURCE", "span", "x"),
                        PoisonVerdict("L_b", True, "", "", "")], run_id="r1", seed=0)
    base = DecisionRow("L_a", "poison", "fail", "UNTRUSTED_SOURCE", "", "", "", "", "0", "r1", "", "")
    assert rows == [base, replace(base, lesson_id="L_b", result="pass", reason_code="")]


def test_run_writes_one_row_per_candidate_and_a_rerun_adds_nothing(tmp_path) -> None:
    store = CandidateStore(tmp_path / "c.jsonl")
    for c in T1 + [DOC]:
        store.append(c)
    before = store.path.read_bytes()
    log = DecisionLog(tmp_path / "decisions.tsv")
    verdicts = run_poison(store, run_id="r1", seed=0, copy="clean", log=log)
    assert [(v.lesson_id, v.passed, v.rule) for v in verdicts] == \
        [(c.lesson.lesson_id, True, "") for c in T1] + [(LID, False, "provenance")]
    assert [r.lesson_id for r in log.read()] == [c.lesson.lesson_id for c in T1] + [LID]
    run_poison(store, run_id="r1", seed=0, copy="clean", log=log)
    assert len(log.read()) == 5
    assert store.path.read_bytes() == before


def test_a_candidate_with_no_paper_text_stops_the_run_before_any_row(tmp_path) -> None:
    store = CandidateStore(tmp_path / "c.jsonl")
    for c in T1 + T2:
        store.append(c)
    log = DecisionLog(tmp_path / "decisions.tsv")
    with pytest.raises(PaperTextMissingError):
        run_poison(store, run_id="r1", seed=0, copy="clean", log=log)
    assert log.read() == []
