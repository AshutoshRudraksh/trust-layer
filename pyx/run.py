"""Pyx runner (spec Section 3, pyx/run.py): wake the worker over arms, grade, and report EVAL.md metrics.

A counted run refuses before any call unless EVAL.md says "Status: FROZEN" and
its sha256 equals the hash the run was given. A repetition is a distinct run id
(the model API has no seed setting). The poison condition is the T1 planted copy
in the no memory arm; it is a condition, not an arm. Keyless mode replays the
recorded log with no key and no network. Metrics follow EVAL.md section 8: pass
rates over conclusive criteria only, and no answer passes while a judged
criterion on it is inconclusive. Tracing is not in this path.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, TextIO, Tuple, Union

from gate.approval_gate import ApprovalGate, DenialLockError
from pyx.approval import OWNER, approval_text, decide, propose
from pyx.arms import ArmContext, earned_ids, no_memory
from pyx.checker import FAIL, PASS
from pyx.decisions import DecisionLog, DecisionRow, rows_from_grade
from pyx.call_log import CallLog
from pyx.grade_run import ReplayMismatchError, grade_keyless, grade_live
from pyx.replay_client import ReplayClient
from pyx.judges import INCONCLUSIVE, JUDGE_DISAGREE, MALFORMED, JudgedVerdict, self_agreement
from pyx.lessons import Candidate, CandidateStore
from pyx.worker import Answer
from pyx.worker_run import AnswerStore, work, work_live

EVAL_PATH = Path(__file__).resolve().parent.parent / "EVAL.md"
GATE_DB = Path(__file__).resolve().parent.parent / "runs" / "approvals.sqlite"
WORDS = {"approve": "APPROVED", "deny": "DENIED"}
PathLike = Union[str, Path]


class EvalNotFrozenError(RuntimeError):
    """EVAL.md is not frozen, or its hash is not the one this run was given."""


def check_frozen(path: PathLike = EVAL_PATH, expected_sha256: str = "") -> str:
    data = Path(path).read_bytes()
    if "Status: FROZEN" not in data.decode("utf-8").splitlines()[:5]:
        raise EvalNotFrozenError(f"{path} does not say Status: FROZEN in its first lines")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise EvalNotFrozenError(f"{path} sha256 {actual} is not the expected {expected_sha256}")
    return actual


def wake(tasks: Sequence[Tuple[str, str]], contexts: Sequence[ArmContext], reps: int, run_id: str,
         log: PathLike, store: PathLike, meta: Optional[Any] = None, keyless: bool = False, counted: bool = True,
         eval_path: PathLike = EVAL_PATH, eval_sha256: str = "") -> List[Answer]:
    if counted:
        check_frozen(eval_path, eval_sha256)
    answers: List[Answer] = []
    client = ReplayClient(CallLog(log, run_id).read(), judge="W", kind="worker") if keyless else None
    for rep in range(reps):
        rid = f"{run_id}_r{rep}"
        for ctx in contexts:
            kw = dict(context=ctx.text, lesson_ids=ctx.lesson_ids)
            if keyless:
                answers += work(tasks, rid, rep, ctx.arm, client, AnswerStore(store), **kw)[0]
            else:
                answers += work_live(tasks, rid, rep, ctx.arm, log, store, meta=meta, **kw)[0]
    if client is not None and client.unused():
        raise ReplayMismatchError(f"unused worker log lines after replay: seq {[l['seq'] for l in client.unused()]}")
    return answers


def poison_condition(reps: int, run_id: str, log: PathLike, store: PathLike, **kw: Any) -> List[Answer]:
    return wake([("T1", "planted")], [no_memory()], reps, f"{run_id}_poison", log, store, **kw)


def grade(answers: Sequence[Answer], log: PathLike, tsv: PathLike, meta: Optional[Any] = None,
          baseten: Optional[Any] = None, keyless: bool = False) -> List[Any]:
    pairs = [(a.task_id, a.answer_text) for a in answers]
    reports = grade_keyless(pairs, log) if keyless else [
        grade_live([p], "grade", log, meta=meta, baseten=baseten)[0] for p in pairs]
    for a, r in zip(answers, reports):
        DecisionLog(tsv).append(rows_from_grade(r, run_id=a.run_id, seed=a.seed, copy=a.copy))
    return reports


def _rate(num: int, den: int) -> float:
    return num / den if den else 0.0


def metrics(answers: Sequence[Answer], reports: Sequence[Any]) -> Dict[str, float]:
    verdicts = [v for r in reports for v in r.verdicts]
    judged = [v for v in verdicts if isinstance(v, JudgedVerdict)]
    conclusive = [v for v in verdicts if v.status in (PASS, FAIL)]
    real = [v for v in judged if v.status != INCONCLUSIVE]
    groups: Dict[Tuple, List[Any]] = defaultdict(list)
    for a, r in zip(answers, reports):
        groups[(a.arm, a.task_id, a.copy)].append(r)
    pairs = {"a": [0, 0], "b": [0, 0]}
    for reps in groups.values():
        for other in reps[1:]:
            for j in pairs:
                first = [getattr(v, f"judge_{j}").verdict for v in reps[0].verdicts if isinstance(v, JudgedVerdict)]
                again = [getattr(v, f"judge_{j}").verdict for v in other.verdicts if isinstance(v, JudgedVerdict)]
                agree, both, _ = self_agreement(first, again)
                pairs[j][0] += agree
                pairs[j][1] += both
    return {
        "criterion_pass_rate": _rate(sum(v.status == PASS for v in conclusive), len(conclusive)),
        "answers_passed": sum(all(v.status == PASS for v in r.verdicts) for r in reports),
        "inconclusive_rate": _rate(sum(v.status == INCONCLUSIVE for v in verdicts), len(verdicts)),
        "judge_disagreement_rate": _rate(sum(JUDGE_DISAGREE in v.flags for v in real), len(real)),
        "judge_b_malformed_rate": _rate(sum(v.judge_b.retries > 0 or v.judge_b.verdict == MALFORMED
                                            for v in judged), len(judged)),
        "self_agreement_a": _rate(*pairs["a"]),
        "self_agreement_b": _rate(*pairs["b"]),
    }


def planted_earned(candidates: Sequence[Candidate], rows: Sequence[DecisionRow],
                   answers: Sequence[Any]) -> List[Candidate]:
    """Earned lessons distilled from planted copy answers, listed for Ashutosh's read against both variants."""
    planted = {a.trace_id for a in answers if a.copy == "planted"}
    earned = earned_ids(rows)
    return [c for c in candidates if c.lesson.lesson_id in earned and c.lesson.created_from_trace_id in planted]


def _approve(args: Any, stdin: TextIO, out: TextIO) -> int:
    try:
        cands = CandidateStore(args.candidates).read()
        rows = DecisionLog(args.decisions).read()
    except (OSError, ValueError) as err:
        print(f"bad input: {err}", file=out)
        return 3
    decided = {r.lesson_id for r in rows if r.step == "approval"}
    passed = {(r.lesson_id, r.step) for r in rows if r.result == "pass"}
    gate = ApprovalGate(db_path=args.gate_db)
    print(f"gate db {args.gate_db}", file=out)
    for cand in sorted(cands, key=lambda c: c.lesson.lesson_id):
        lid, sha = cand.lesson.lesson_id, cand.provenance.text_sha256
        if lid in decided or not {(lid, "poison"), (lid, "replay")} <= passed:
            continue
        replay = next(r for r in rows if r.lesson_id == lid and r.step == "replay" and r.result == "pass")
        print(approval_text(cand, replay), file=out)
        print("Type approve or deny:", file=out)
        word = stdin.readline().strip().lower()
        if word not in WORDS:
            print(f"{lid} skipped, nothing written", file=out)
            continue
        try:
            record = propose(gate, cand, rows, f"approve_{lid}_{sha[:8]}")
        except DenialLockError:
            print(f"{lid} locked after a denial, nothing written", file=out)
            continue
        row = decide(gate, record, cand, WORDS[word], OWNER, args.run_id, 0)
        DecisionLog(args.decisions).append([row])
        print(f"{lid} {row.reason_code}", file=out)
    return 0


def main(argv: Optional[Sequence[str]] = None, stdin: TextIO = sys.stdin, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="python -m pyx.run")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("approve", "check-eval"):
        p = sub.add_parser(name)
        p.add_argument("--eval", default=str(EVAL_PATH))
        p.add_argument("--eval-sha256", default="")
    ap = sub.choices["approve"]
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--gate-db", default=str(GATE_DB))
    ap.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        actual = check_frozen(args.eval, args.eval_sha256)
    except EvalNotFrozenError as err:
        print(f"refused: {err}", file=out)
        return 2
    print(f"EVAL frozen, sha256 {actual}", file=out)
    return _approve(args, stdin, out) if args.command == "approve" else 0


if __name__ == "__main__":
    sys.exit(main())
