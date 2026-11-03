"""PR H9b tests: phase 1 of the counted run (plan H9 tests 7 to 12). Fakes and local files only; no network."""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pyx.phase import phase1
from pyx.run import main

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"


class Fake:
    def __init__(self, ledger=None, cost=0.0):
        self.calls, self.ledger, self.cost = [], ledger, cost

    def respond(self, prompt, **kw):
        if self.ledger is not None:
            self.ledger.spent += self.cost
        if prompt.startswith("You write the paper"):
            kind, text = "worker", (FIX / ("T1_bad.md" if "2303.11366" in prompt[:300] else "T2_bad.md")).read_text()
        elif prompt.startswith("You write lessons"):
            crit = re.search(r"Failed criterion: (\S+)", prompt).group(1)
            kind, text = "distill", f"LESSON: Before submitting, recheck the item graded as {crit} for omissions."
        else:
            kind, text = "judge", "FAIL"
        self.calls.append(kind)
        return NS(output_text=text, input_tokens=1, output_tokens=1, cost_usd=0.0, model="m")

    chat = respond


class Ledger:
    def __init__(self):
        self.spent = 0.0

    def total_usd(self, provider):
        return self.spent if provider == "meta" else 0.0


def _eval(tmp_path, status="FROZEN", reps=3):
    p = tmp_path / f"EVAL_{status}.md"
    p.write_text(f"# EVAL\nStatus: {status}\n## 3. Seeds\nA seed is a repetition. {reps} repetitions.\n")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def _live(ledger=None, cost=0.0):
    fake = Fake(ledger, cost)
    return fake, {"worker": fake, "a": fake, "b": fake, "distill": fake}


def _go(tmp_path, out, live, ledger=None, **kw):
    ev, h = _eval(tmp_path)
    return phase1(out, "R", h, 3, live=live, ledger=ledger or Ledger(), eval_path=ev, **kw)


def _rows(path):
    return list(csv.DictReader(path.open(), delimiter="\t")) if path.exists() else []


def test_draft_eval_mismatched_hash_or_fewer_reps_exit_2_and_write_nothing(tmp_path, capsys) -> None:
    fake, live = _live()
    draft, hd = _eval(tmp_path, "DRAFT")
    frozen, h = _eval(tmp_path)
    out = tmp_path / "out"
    assert phase1(out, "R", hd, 3, live=live, ledger=Ledger(), eval_path=draft) == 2
    assert phase1(out, "R", "0" * 64, 3, live=live, ledger=Ledger(), eval_path=frozen) == 2
    assert phase1(out, "R", h, 1, live=live, ledger=Ledger(), eval_path=frozen) == 2
    assert main(["phase1", "--run-id", "R", "--out", str(out), "--eval-sha256", "0" * 64, "--reps", "3"]) == 2
    assert fake.calls == [] and not out.exists()


def test_call_counts_match_the_plan_and_only_repetition_0_candidates_are_replayed(tmp_path) -> None:
    fake, live = _live()
    out = tmp_path / "out"
    assert _go(tmp_path, out, live) == 0
    decisions = _rows(out / "decisions.tsv")
    r0 = [r for r in decisions if r["step"] == "poison" and r["result"] == "pass"]
    replayed = [r for r in decisions if r["step"] == "replay"]
    assert sorted(r["lesson_id"] for r in replayed) == sorted(r["lesson_id"] for r in r0) and r0
    distilled = sum(len(f.read_text().splitlines()) for f in out.glob("candidates_r*_*.jsonl"))
    assert fake.calls.count("distill") == distilled  # one call per failed criterion, all three repetitions
    unique = {r["lesson_id"] for r in replayed}  # a text found in both copies shares one id and one replay run
    assert fake.calls.count("worker") == 9 + 2 * 3 + len(unique) * 2 * 3
    for rep in (1, 2):
        assert (out / f"candidates_r{rep}_clean.jsonl").read_text()  # written for the record, never replayed
    assert {r["run_id"] for r in _rows(out / "replay_reps.tsv")} == {"R_r0", "R_r1", "R_r2"}
    assert {r["lesson_id"] for r in _rows(out / "replay_reps.tsv")} == {r["lesson_id"] for r in replayed}
    assert "awaiting pairs" in (out / "status.txt").read_text()
    assert (out / "candidates_for_pairs.txt").read_text().count("\n") >= len(r0)


def test_replay_baselines_are_paired_runs_never_cycle_0_answers(tmp_path) -> None:
    fake, live = _live()
    out = tmp_path / "out"
    _go(tmp_path, out, live)
    answers = (out / "answers.jsonl").read_text()
    for rep in range(3):
        assert f'"R_r{rep}_replay_' in answers  # the paired run without the lesson, in its own repetition
    base_ids = {r["run_id"] for r in _rows(out / "replay_reps.tsv")}
    assert base_ids.isdisjoint({f"R_poison_r{i}" for i in range(3)})


def test_first_invocation_stops_and_resume_runs_only_the_named_pair_with_zero_repeat_calls(tmp_path) -> None:
    fake, live = _live()
    out = tmp_path / "out"
    _go(tmp_path, out, live)
    before = list(fake.calls)
    ids = [r["lesson_id"] for r in _rows(out / "decisions.tsv") if r["step"] == "replay"][:2]
    pairs = out / "pairs.txt"
    pairs.write_text(f"{ids[0]} {ids[1]}\n")
    assert _go(tmp_path, out, live, pairs=pairs) == 0
    assert fake.calls[len(before):].count("worker") == 2 * 3 and "distill" not in fake.calls[len(before):]
    assert "ready for approval" in (out / "status.txt").read_text()
    assert '"resolved"' in (out / "pairs.json").read_text()
    again = len(fake.calls)
    assert _go(tmp_path, out, live, pairs=pairs) == 0 and len(fake.calls) == again


def test_passing_a_cap_writes_abort_and_exits_4_with_no_further_calls(tmp_path) -> None:
    ledger = Ledger()
    fake, live = _live(ledger, cost=0.3)
    out = tmp_path / "out"
    assert _go(tmp_path, out, live, ledger=ledger) == 4
    assert "passed $0.8" in (out / "abort.txt").read_text()
    n = len(fake.calls)
    assert _go(tmp_path, out, live, ledger=ledger) == 4 and len(fake.calls) == n
