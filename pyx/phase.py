"""PR H9b: phase 1 of the counted run (EVAL.md sections 3, 4, 6, 7 and 11; plan H9).

One engine serves every model call first from the call log and only then live, so a resumed or keyless
invocation makes no repeat calls. No tracing import and no HTTP client here: live clients are passed in.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agents.baseten_client import BASETEN_MODEL
from pyx.arms import ArmContext, no_memory
from pyx.call_log import CallLog, _sha256
from pyx.checker import check_answer
from pyx.decisions import DecisionLog, rows_from_grade
from pyx.distill import META_MODEL, distill_reports
from pyx.grade_run import _check_against_log
from pyx.judges import grade_answer
from pyx.lessons import CandidateStore
from pyx.poison_run import run_poison
from pyx.recording import RecordingClient
from pyx.replay import pair_reps, replay_reps, without_runs
from pyx.replay_client import ReplayClient, ReplayMissError
from pyx.rubric import load_rubric
from pyx.run import EVAL_PATH, EvalNotFrozenError, check_frozen
from pyx.worker import WORKER_MODEL
from pyx.worker_run import AnswerStore, work

CAPS = {"meta": 0.80, "baseten": 2.50}
CYCLE0 = (("T1", "clean"), ("T2", "clean"), ("T1", "planted"))
SPEC = {"worker": ("W", WORKER_MODEL, "responses", "worker"), "a": ("A", META_MODEL, "responses", "judge"),
        "b": ("B", BASETEN_MODEL, "chat_completions", "judge"), "distill": ("D", META_MODEL, "responses", "distill")}


class BudgetAbort(RuntimeError):
    pass


def eval_reps(path: Path) -> int:
    found = re.search(r"(\d+) repetitions\.", Path(path).read_text(encoding="utf-8"))
    return int(found.group(1)) if found else 0


class LogFirst:
    """Serve from the log when an unused line matches, else call live and record; keyless has no live."""

    def __init__(self, lines: List[Dict[str, Any]], live: Any, log: CallLog, judge: str, model: str,
                 endpoint: str, kind: str) -> None:
        self.replay = ReplayClient(lines, judge=judge, kind=kind)
        self.live = live and RecordingClient(live, log, judge=judge, model=model, endpoint=endpoint, kind=kind)

    def respond(self, prompt: str, **params: Any) -> Any:
        try:
            return self.replay.respond(prompt, **params)
        except ReplayMissError:
            if not self.live:
                raise
            return self.live.respond(prompt, **params)

    chat = respond


class Engine:
    def __init__(self, out: Path, run_id: str, live: Optional[Dict[str, Any]], ledger: Any,
                 src_log: Optional[Path] = None) -> None:
        self.out, self.run_id, self.ledger = out, run_id, ledger
        self.log = CallLog(out / "calls.jsonl", run_id)
        lines = CallLog(src_log or self.log.path, run_id).read()
        self.c = {k: LogFirst(lines, (live or {}).get(k), self.log, *v) for k, v in SPEC.items()}
        self.checks, self.used = [l for l in lines if l.get("kind") == "checker"], set()
        self.store, self.keyless = AnswerStore(out / "answers.jsonl"), not live
        start = out / "budget_start.json"
        if ledger is not None and not start.exists():
            start.write_text(json.dumps({p: ledger.total_usd(p) for p in CAPS}) + "\n")

    def check_budget(self) -> None:
        if (self.out / "abort.txt").exists():
            raise BudgetAbort("aborted earlier")
        if self.ledger is None:
            return
        start = json.loads((self.out / "budget_start.json").read_text())
        for p, cap in CAPS.items():
            new = self.ledger.total_usd(p) - start[p]
            if new > cap:
                (self.out / "abort.txt").write_text(f"ABORT: new {p} spend ${new:.8f} passed ${cap}\n")
                raise BudgetAbort(p)

    def _grade(self, task_id: str, text: str) -> Any:
        rubric, sha = load_rubric(task_id, role="checker"), _sha256(text)
        for i, line in enumerate(self.checks):
            if i not in self.used and line["task_id"] == task_id and line["answer_sha256"] == sha:
                self.used.add(i)
                _check_against_log(task_id, text, line)
                break
        else:
            if self.keyless:
                raise ReplayMissError(f"no unused checker line for {task_id} {sha[:12]}")
            self.log.append_checker(task_id, text, rubric, check_answer(text, rubric))
        return grade_answer(text, task_id, self.c["a"], self.c["b"])

    def cell(self, task_id: str, copy: str, rid: str, seed: int, ctx: ArmContext, tsv: str) -> Tuple[Any, Any]:
        self.check_budget()
        new = self.store.find((rid, seed, ctx.arm, task_id, copy)) is None
        answers, faults = work([(task_id, copy)], rid, seed, ctx.arm, self.c["worker"], self.store, ctx.text,
                               ctx.lesson_ids)
        if faults:
            (self.out / "abort.txt").write_text(f"ABORT: budget stop: {faults}\n")
            raise BudgetAbort(faults[0])
        report = self._grade(task_id, answers[0].answer_text)
        if new:
            DecisionLog(self.out / tsv).append(rows_from_grade(report, rid, seed, copy))
        return answers[0], report

    def runner(self) -> Any:
        def run(task_id: str, ctx: ArmContext, rid: str) -> Any:
            return self.cell(task_id, "clean", rid, int(rid[len(self.run_id) + 2]), ctx, "replay_grades.tsv")[1]
        return run


def _stage1(eng: Engine, reps: int) -> None:
    out, rid0 = eng.out, eng.run_id
    for rep in range(reps):
        for task_id, copy in CYCLE0:
            rid = f"{rid0}_r{rep}" if copy == "clean" else f"{rid0}_poison_r{rep}"
            answer, report = eng.cell(task_id, copy, rid, rep, no_memory(), "decisions.tsv")
            eng.check_budget()
            cands, faults = distill_reports([(report, answer.answer_text)], rid, eng.c["distill"])
            store = CandidateStore(out / f"candidates_r{rep}_{copy}.jsonl")
            for c in cands:
                store.append(c)
    decisions, passed = DecisionLog(out / "decisions.tsv"), []
    for copy in ("clean", "planted"):
        store = CandidateStore(out / f"candidates_r0_{copy}.jsonl")
        verdicts = run_poison(store, f"{rid0}_poison_check", 0, copy, decisions)
        ok = {v.lesson_id for v in verdicts if v.passed}
        passed += [(c, copy) for c in store.read() if c.lesson.lesson_id in ok]
    baselines = _baselines(eng, reps)
    listing = []
    for cand, copy in passed:
        row, detail = replay_reps(cand, ["T1", "T2"], eng.runner(), baselines, rid0, copy)
        decisions.append([row])
        DecisionLog(out / "replay_reps.tsv").append(detail)
        listing.append(f"{cand.lesson.lesson_id}\t{copy}\t{row.result}\t{row.flags}\t{cand.lesson.text}")
    (out / "candidates_for_pairs.txt").write_text("".join(l + "\n" for l in listing))


def _baselines(eng: Engine, reps: int) -> List[Any]:
    return [without_runs(["T1", "T2"], eng.runner(), f"{eng.run_id}_r{i}", i) for i in range(reps)]


def _replayed(out: Path) -> Dict[str, Any]:
    cands = {c.lesson.lesson_id: c for copy in ("clean", "planted")
             for c in CandidateStore(out / f"candidates_r0_{copy}.jsonl").read()}
    listed = (out / "candidates_for_pairs.txt").read_text().splitlines()
    return {l.split("\t")[0]: cands[l.split("\t")[0]] for l in listed}


def _stage2(eng: Engine, reps: int, pairs: Path) -> None:
    text = Path(pairs).read_text(encoding="utf-8")
    named = [] if text.strip().lower() == "none" else [tuple(l.split()) for l in text.splitlines() if l.strip()]
    cands = _replayed(eng.out)
    if any(len(p) != 2 or not set(p) <= set(cands) for p in named):
        raise ValueError(f"{pairs}: each line needs two replayed lesson ids, or the single word none")
    baselines = _baselines(eng, reps) if named else []
    verdicts = [pair_reps(cands[a], cands[b], ["T1", "T2"], eng.runner(), baselines, eng.run_id) for a, b in named]
    if Path(pairs) != eng.out / "pairs.txt":
        (eng.out / "pairs.txt").write_text(text)
    (eng.out / "pairs.json").write_text(json.dumps(verdicts, indent=1, sort_keys=True) + "\n")


def phase1(out: Any, run_id: str, eval_sha256: str, reps: int, pairs: Optional[Path] = None,
           live: Optional[Dict[str, Any]] = None, ledger: Any = None, src_log: Optional[Path] = None,
           eval_path: Path = EVAL_PATH) -> int:
    try:
        check_frozen(eval_path, eval_sha256)
    except EvalNotFrozenError as exc:
        print(f"refused: {exc}")
        return 2
    if reps != eval_reps(eval_path):
        print(f"refused: --reps {reps} differs from the {eval_reps(eval_path)} repetitions frozen in EVAL.md")
        return 2
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    eng = Engine(out, run_id, live, ledger, src_log)
    status = out / "status.txt"
    try:
        if not (out / "candidates_for_pairs.txt").exists():
            _stage1(eng, reps)
        if pairs is None:
            status.write_text("awaiting pairs\n")
        elif not (out / "pairs.json").exists():
            _stage2(eng, reps, pairs)
        if pairs is not None:
            status.write_text("ready for approval\n")
    except BudgetAbort:
        print((out / "abort.txt").read_text().strip())
        return 4
    print(status.read_text().strip())
    return 0
