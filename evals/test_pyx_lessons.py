"""PR E1 tests: Lesson and Provenance records (spec Section 4) and the candidate store."""
from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from pyx.lessons import (TEXT_CAP, Candidate, CandidateStore, Lesson, LessonError, Provenance,
                         make_lesson_id)
from pyx.call_log import TornLogError

TEXT = "State each result with the table it comes from."
SHA = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
LID = make_lesson_id("T1.C3", TEXT)
LESSON = Lesson(lesson_id=LID, text=TEXT, scope="paper_anatomy", created_from_trace_id="tr1",
                fixes_criterion_id="T1.C3", status="candidate", version=1)
PROV = Provenance(lesson_id=LID, source_trace_id="tr1", source_paper_id="2303.11366v4",
                  source_kind="graded_failure", distiller_model="muse-spark-1.3-contributor", text_sha256=SHA)


def test_lesson_id_names_the_criterion_and_the_text_hash() -> None:
    assert LID == f"L_T1.C3_{SHA[:8]}"


def test_records_carry_every_spec_field() -> None:
    assert (LESSON.status, LESSON.version, LESSON.scope) == ("candidate", 1, "paper_anatomy")
    assert (PROV.replay_run_ids, PROV.approver, PROV.approved_at) == ((), "", "")


def test_status_is_a_closed_set() -> None:
    with pytest.raises(LessonError, match="status"):
        replace(LESSON, status="admitted")


def test_source_kind_is_a_closed_set() -> None:
    with pytest.raises(LessonError, match="source_kind"):
        replace(PROV, source_kind="web_page")


@pytest.mark.parametrize("text", ["", "   ", "x" * (TEXT_CAP + 1)])
def test_empty_or_overlong_text_is_refused(text: str) -> None:
    with pytest.raises(LessonError, match="text"):
        replace(LESSON, text=text)


def test_text_changed_without_its_hash_is_refused() -> None:
    with pytest.raises(LessonError, match="text_sha256"):
        Candidate(replace(LESSON, text=TEXT + " Always."), PROV)


def test_provenance_must_name_the_same_lesson() -> None:
    with pytest.raises(LessonError, match="lesson_id"):
        Candidate(LESSON, replace(PROV, lesson_id="L_other"))


def test_store_round_trips_and_skips_an_identical_repeat(tmp_path) -> None:
    store = CandidateStore(tmp_path / "candidates.jsonl")
    assert store.append(Candidate(LESSON, PROV)) is True
    assert store.append(Candidate(LESSON, PROV)) is False
    assert store.read() == [Candidate(LESSON, PROV)]


def test_store_refuses_a_conflicting_lesson_id(tmp_path) -> None:
    store = CandidateStore(tmp_path / "candidates.jsonl")
    store.append(Candidate(LESSON, PROV))
    with pytest.raises(LessonError, match="conflict"):
        store.append(Candidate(replace(LESSON, created_from_trace_id="tr2"), replace(PROV, source_trace_id="tr2")))


def test_store_reports_a_torn_last_line(tmp_path) -> None:
    path = tmp_path / "candidates.jsonl"
    CandidateStore(path).append(Candidate(LESSON, PROV))
    path.write_text(path.read_text() + '{"lesson": ')
    with pytest.raises(TornLogError):
        CandidateStore(path).read()
