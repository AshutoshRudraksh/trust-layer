"""PR H9c tests: phase 2 of the counted run and keyless reruns (plan H9 tests 13 to 18). Fakes only; no network."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from pyx.decisions import DecisionLog, DecisionRow
from pyx.lessons import CandidateStore
from pyx.phase import phase1, phase2
from evals.test_pyx_phase1 import Ledger, _eval, _live, _rows

PHASE = Path(__file__).resolve().parent.parent / "pyx" / "phase.py"


def _approve(out, ids, word="HUMAN_APPROVED"):
    DecisionLog(out / "decisions.tsv").append([DecisionRow(i, "approval", "pass" if word == "HUMAN_APPROVED" else "fail",
                                                           word, "", "", "", "", "0", "R", "", "", "")
                                               for i in ids])


def _passing(out, ids):
    """Mark replay passes, as a fixed lesson would earn, so the approval gate has work."""
    DecisionLog(out / "decisions.tsv").append([DecisionRow(i, "replay", "pass", "", "x", "", "", "", "0", "R_replay",
                                                           "reps=F,F,F", "T1", "clean") for i in ids])


def _phase1_done(tmp_path, live, pair=True):
    ev, h = _eval(tmp_path)
    out = tmp_path / "out"
    assert phase1(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    ids = [l.split("\t")[0] for l in (out / "candidates_for_pairs.txt").read_text().splitlines()]
    (out / "pairs.txt").write_text(f"{ids[0]} {ids[1]}\n" if pair else "none\n")
    assert phase1(out, "R", h, 3, pairs=out / "pairs.txt", live=live, ledger=Ledger(), eval_path=ev) == 0
    return out, ev, h, ids


def test_phase2_exits_3_until_pairs_exist_and_every_admissible_lesson_has_an_approval_row(tmp_path) -> None:
    fake, live = _live()
    ev, h = _eval(tmp_path)
    out = tmp_path / "out"
    assert phase1(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 3
    ids = [l.split("\t")[0] for l in (out / "candidates_for_pairs.txt").read_text().splitlines()]
    (out / "pairs.txt").write_text("none\n")
    phase1(out, "R", h, 3, pairs=out / "pairs.txt", live=live, ledger=Ledger(), eval_path=ev)
    _passing(out, ids[2:4])
    n = len(fake.calls)
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 3 and len(fake.calls) == n
    _approve(out, ids[2:4])
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    assert phase2(out, "R", h, 1, live=live, ledger=Ledger(), eval_path=ev) == 2


def test_arm_contexts_follow_a5_to_a7(tmp_path) -> None:
    fake, live = _live()
    out, ev, h, ids = _phase1_done(tmp_path, live)
    pairs = json.loads((out / "pairs.json").read_text())
    pairs[0]["resolved"] = False  # a together break: neither lesson is carried
    (out / "pairs.json").write_text(json.dumps(pairs, indent=1, sort_keys=True) + "\n")
    _passing(out, ids[:3])
    _approve(out, ids[:3])
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    answers = [json.loads(l) for l in (out / "answers.jsonl").read_text().splitlines()]
    c1 = [a for a in answers if a["run_id"].startswith("R_c1_r")]
    assert len(c1) == 4 * 2 * 3
    earned = {tuple(a["lesson_ids"]) for a in c1 if a["arm"] == "earned_lessons"}
    assert earned == {(ids[2],)}  # identical across the three repetitions, minus the unresolved pair
    free = {tuple(a["lesson_ids"]) for a in c1 if a["arm"] == "free_lessons"}
    every = {c.lesson.lesson_id for c in CandidateStore(out / "candidates_r0.jsonl").read()}
    assert len(free) == 1 and set(next(iter(free))) == every >= set(ids)  # every rep 0 candidate, poison fails too
    contexts = (out / "contexts.tsv").read_text()
    for rep in range(3):
        cycle0 = next(a for a in answers if a["run_id"] == f"R_r{rep}" and a["task_id"] == "T1")
        assert f"raw_traces\tT1\t{rep}\t{cycle0['trace_id']}" in contexts


def test_metrics_report_self_agreement_per_task_and_per_arm_and_task(tmp_path) -> None:
    fake, live = _live()
    out, ev, h, ids = _phase1_done(tmp_path, live, pair=False)
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    m = json.loads((out / "metrics.json").read_text())
    for key in ("cycle0/T1", "cycle0/T2", "cycle0/T1_planted", "cycle1/no_memory/T1", "cycle1/earned_lessons/T2"):
        assert {"self_agreement_a", "self_agreement_b", "inconclusive_rate", "judge_disagreement_rate",
                "judge_b_malformed_rate"} <= set(m[key]), key


def test_planted_listing_holds_exactly_the_earned_lessons_from_planted_answers(tmp_path) -> None:
    fake, live = _live()
    out, ev, h, ids = _phase1_done(tmp_path, live, pair=False)
    planted = [c for c in CandidateStore(out / "candidates_r0_planted.jsonl").read()]
    clean = {c.lesson.lesson_id for c in CandidateStore(out / "candidates_r0_clean.jsonl").read()}
    only = [c.lesson.lesson_id for c in planted if c.lesson.lesson_id not in clean]
    chosen = only[:1] + sorted(clean)[:1]
    _passing(out, chosen)
    _approve(out, chosen)
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    listing = (out / "planted_earned.md").read_text()
    assert re.findall(r"^## (\S+)", listing, re.M) == only[:1]


def test_keyless_reruns_reproduce_every_output_byte_for_byte_with_no_unused_lines(tmp_path, capsys) -> None:
    fake, live = _live()
    out, ev, h, ids = _phase1_done(tmp_path, live)
    _passing(out, ids[2:3])
    _approve(out, ids[2:3])
    assert phase2(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    calls = len(fake.calls)
    total = len((out / "calls.jsonl").read_text().splitlines())
    capsys.readouterr()
    k = tmp_path / "keyless"
    src = out / "calls.jsonl"
    assert phase1(k, "R", h, 3, src_log=src, eval_path=ev) == 0
    shutil.copy(out / "pairs.txt", k / "pairs.txt")
    assert phase1(k, "R", h, 3, pairs=k / "pairs.txt", src_log=src, eval_path=ev) == 0
    _passing(k, ids[2:3])
    _approve(k, ids[2:3])
    assert phase2(k, "R", h, 3, src_log=src, eval_path=ev) == 0
    served = {int(n) for line in re.findall(r"served log seqs (\S*)", capsys.readouterr().out)
              for n in line.split(",") if n}
    assert served == set(range(total)) and len(fake.calls) == calls  # every line served, no unused line
    for f in sorted(p.name for p in out.iterdir() if p.name not in ("calls.jsonl", "budget_start.json")):
        assert (k / f).read_bytes() == (out / f).read_bytes(), f


def test_phase_module_has_no_tracing_import_and_no_http_client() -> None:
    src = PHASE.read_text()
    for bad in ("requests", "httpx", "urllib", "socket", "tracing", "opentelemetry", "meta_client"):
        assert not re.search(rf"^\s*(from|import) \S*{bad}", src, re.M), bad
