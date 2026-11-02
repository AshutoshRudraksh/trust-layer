"""PR H4 tests: the runner (plan H tests 16 to 20). Fakes and local files only; no network."""
from __future__ import annotations

import hashlib
import socket
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pyx.arms import free_lessons, no_memory
from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import CandidateStore
from pyx.run import EvalNotFrozenError, check_frozen, grade, metrics, planted_earned, poison_condition, wake
from pyx.worker_run import AnswerStore

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"
CANDS = CandidateStore(FIX / "replay" / "e4_distill_candidates.jsonl").read()
TASKS = [("T1", "clean"), ("T2", "clean")]


class Fake:
    def __init__(self, judge="FAIL"):
        self.judge, self.calls = judge, 0

    def respond(self, prompt, **kw):
        self.calls += 1
        name = "T1_bad" if "2303.11366" in prompt[:300] else "T2_bad"
        text = (FIX / f"{name}.md").read_text() if prompt.startswith("You write the paper") else self.judge
        return NS(output_text=text, input_tokens=1, output_tokens=1, cost_usd=0.0, model="m")

    chat = respond


def _eval(tmp_path, status="FROZEN"):
    p = tmp_path / f"EVAL_{status}.md"
    p.write_text(f"# EVAL\nStatus: {status}\n")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def test_counted_run_refuses_unless_eval_is_frozen_with_matching_hash(tmp_path) -> None:
    draft, h = _eval(tmp_path, "DRAFT")
    with pytest.raises(EvalNotFrozenError):
        check_frozen(draft, h)
    frozen, h = _eval(tmp_path)
    assert check_frozen(frozen, h) == h
    with pytest.raises(EvalNotFrozenError):
        check_frozen(frozen, "0" * 64)
    fake = Fake()
    with pytest.raises(EvalNotFrozenError):
        wake(TASKS, [no_memory()], 1, "r", tmp_path / "l.jsonl", tmp_path / "a.jsonl", meta=fake,
             eval_path=draft, eval_sha256=h)
    assert fake.calls == 0


def test_wake_calls_arms_times_tasks_times_repetitions(tmp_path) -> None:
    ev, h = _eval(tmp_path)
    fake = Fake()
    answers = wake(TASKS, [no_memory(), free_lessons(CANDS[:2])], 3, "r", tmp_path / "l.jsonl", tmp_path / "a.jsonl",
                   meta=fake, eval_path=ev, eval_sha256=h)
    assert fake.calls == len(answers) == 2 * 2 * 3
    assert len({a.run_id for a in answers}) == 3 and {a.seed for a in answers} == {0, 1, 2}


def test_poison_condition_is_t1_planted_in_no_memory_with_planted_rows(tmp_path) -> None:
    ev, h = _eval(tmp_path)
    answers = poison_condition(2, "r", tmp_path / "l.jsonl", tmp_path / "a.jsonl", meta=Fake(),
                               eval_path=ev, eval_sha256=h)
    assert {(a.task_id, a.copy, a.arm) for a in answers} == {("T1", "planted", "no_memory")}
    grade(answers, tmp_path / "l.jsonl", tmp_path / "d.tsv", meta=Fake(), baseten=Fake())
    assert {r.copy for r in DecisionLog(tmp_path / "d.tsv").read()} == {"planted"}


def test_keyless_rerun_reproduces_every_row_with_no_keys_and_no_network(tmp_path, monkeypatch) -> None:
    ev, h = _eval(tmp_path)
    log = tmp_path / "l.jsonl"
    live = wake(TASKS, [no_memory()], 2, "r", log, tmp_path / "a.jsonl", meta=Fake(), eval_path=ev, eval_sha256=h)
    grade(live, log, tmp_path / "live.tsv", meta=Fake(), baseten=Fake())
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    def refuse(*a, **k):
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    again = wake(TASKS, [no_memory()], 2, "r", log, tmp_path / "k.jsonl", keyless=True, counted=False)
    grade(again, log, tmp_path / "k.tsv", keyless=True)
    assert again == live
    assert (tmp_path / "k.tsv").read_bytes() == (tmp_path / "live.tsv").read_bytes()


def test_metrics_use_conclusive_criteria_and_report_the_four_rates(tmp_path) -> None:
    ev, h = _eval(tmp_path)
    answers = wake(TASKS, [no_memory()], 2, "r", tmp_path / "l.jsonl", tmp_path / "a.jsonl", meta=Fake(),
                   eval_path=ev, eval_sha256=h)
    reports = grade(answers, tmp_path / "l.jsonl", tmp_path / "d.tsv", meta=Fake("PASS"), baseten=Fake("maybe"))
    m = metrics(answers, reports)
    assert m["inconclusive_rate"] == pytest.approx(4 / 32)
    assert m["answers_passed"] == 0 and m["judge_b_malformed_rate"] == 1.0
    assert m["criterion_pass_rate"] == pytest.approx(sum(
        v.status == "PASS" for r in reports for v in r.verdicts) / 28)
    assert set(m) >= {"judge_disagreement_rate", "self_agreement_a", "self_agreement_b"}


def test_planted_earned_lists_lessons_from_planted_answers_only() -> None:
    a = NS(copy="planted", trace_id=CANDS[0].lesson.created_from_trace_id)
    rows = [DecisionRow(c.lesson.lesson_id, s, "pass", "HUMAN_APPROVED" if s == "approval" else "", "", "", "", "",
                        "0", "r", "", "", "") for c in CANDS for s in ("poison", "replay", "approval")]
    listed = planted_earned(CANDS, rows, [a])
    assert listed and all(c.lesson.created_from_trace_id == a.trace_id for c in listed)


def test_runtime_modules_do_not_name_tracing() -> None:
    for m in ("run", "arms", "replay", "approval"):
        assert "agents.tracing" not in (Path(__file__).resolve().parent.parent / "pyx" / f"{m}.py").read_text()
