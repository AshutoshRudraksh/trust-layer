"""Pyx G3 proof: three worker answers live on muse-spark-1.3-contributor, graded live, then replayed keylessly.

  python3 scripts/pyx_worker_proof.py live LOG ANSWERS TSV      live calls, needs MODEL_API_KEY and BASETEN_API_KEY
  python3 scripts/pyx_worker_proof.py keyless LOG ANSWERS TSV   no key, no network: replays LOG

Tasks: T1 clean, T1 planted, T2 clean; one seed; arm no_memory; worker cap 6144,
worker timeout 120 s.
Each grade row carries its answer's copy in decisions.tsv column 13. Prints only
whether each key name is set, never a value. The live mode stops once new Meta
spend passes $0.03 or new Baseten spend passes $0.05; a budget stop propagates.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.spend_ledger import SpendLedger  # noqa: E402
from pyx.call_log import CallLog  # noqa: E402
from pyx.decisions import DecisionLog, rows_from_grade  # noqa: E402
from pyx.grade_run import grade_keyless, grade_live  # noqa: E402
from pyx.worker import worker_client  # noqa: E402
from pyx.worker_run import AnswerStore, answers_for_grading, work_keyless, work_live  # noqa: E402

TASKS = [("T1", "clean"), ("T1", "planted"), ("T2", "clean")]
RUN_ID, SEED, ARM = "g3_proof", 0, "no_memory"
ABORT = {"meta": 0.03, "baseten": 0.05}


def _keys() -> str:
    return " ".join(f"{n}={'set' if os.getenv(n) else 'unset'}" for n in
                    ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"))


def _check_abort(ledger: SpendLedger, start: dict) -> None:
    for p, cap in ABORT.items():
        new = ledger.total_usd(p) - start[p]
        if new > cap:
            sys.exit(f"ABORT: new {p} spend ${new:.8f} passed ${cap}")


def live(log: str, answers: str, tsv: str) -> None:
    from agents.baseten_client import BasetenClient
    from agents.meta_client import MetaModelClient

    print(f"mode=live {_keys()}")
    ledger = SpendLedger()
    start = {p: ledger.total_usd(p) for p in ABORT}
    print(f"ledger before: meta=${start['meta']:.8f} baseten=${start['baseten']:.8f}")
    meta, baseten = MetaModelClient(ledger=ledger), BasetenClient(ledger=ledger)
    worker = worker_client(ledger=ledger)  # 120 s timeout; the judges keep 40 s
    for task in TASKS:
        _, faults = work_live([task], RUN_ID, SEED, ARM, log, answers, meta=worker)
        print(f"  worker {task}: faults={faults}")
        _check_abort(ledger, start)
    for a in AnswerStore(answers).read():
        report = grade_live([(a.task_id, a.answer_text)], RUN_ID, log, meta=meta, baseten=baseten)[0]
        DecisionLog(tsv).append(rows_from_grade(report, run_id=RUN_ID, seed=SEED, copy=a.copy))
        _check_abort(ledger, start)
    for line in CallLog(log, RUN_ID).read():
        if line["kind"] != "checker":
            print(f"  call seq={line['seq']} kind={line['kind']} role={line['judge']} model={line['model']} "
                  f"outcome={line['outcome']} in={line['input_tokens']} out={line['output_tokens']} "
                  f"reasoning={line['reasoning_tokens']} cost=${line['cost_usd']:.8f} latency_s={line['latency_s']}")
    end = {p: ledger.total_usd(p) for p in start}
    print(f"ledger after: meta=${end['meta']:.8f} of $40 hard stop, baseten=${end['baseten']:.8f} of $25 guide; "
          f"new spend meta=${end['meta'] - start['meta']:.8f} baseten=${end['baseten'] - start['baseten']:.8f}")


def replay(log, answers, tsv) -> list:
    """Keyless: worker answers from the log, then grading from the log; any miss or unused line fails."""
    _, faults = work_keyless(TASKS, RUN_ID, SEED, ARM, log, answers)
    stored = AnswerStore(answers).read()
    reports = grade_keyless(answers_for_grading(AnswerStore(answers), RUN_ID), log)
    for a, report in zip(stored, reports):
        DecisionLog(tsv).append(rows_from_grade(report, run_id=RUN_ID, seed=SEED, copy=a.copy))
    return faults


def keyless(log: str, answers: str, tsv: str) -> None:
    print(f"mode=keyless {_keys()}")
    faults = replay(log, answers, tsv)
    print(f"replayed {len(CallLog(log, RUN_ID).read())} log lines, every line served; faults={faults}")


if __name__ == "__main__":
    {"live": live, "keyless": keyless}[sys.argv[1]](*sys.argv[2:5])
