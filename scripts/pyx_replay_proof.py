"""Pyx D3 proof: grade the four fixture answers live with recording, replay keylessly, compare rows.

  python3 scripts/pyx_replay_proof.py live LOG TSV      live calls, needs MODEL_API_KEY and BASETEN_API_KEY
  python3 scripts/pyx_replay_proof.py keyless LOG TSV   no key, no network: replays LOG
  python3 scripts/pyx_replay_proof.py compare TSV TSV   row by row comparison

Prints only whether each key name is set, never a value. The live mode stops
after any answer once new spend passes $0.05.
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
from pyx.judges import JudgedVerdict  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "evals" / "fixtures" / "pyx"
ANSWERS = [(f[:2], f, (FIX / f"{f}.md").read_text()) for f in ("T1_good", "T1_bad", "T2_good", "T2_bad")]
RUN_ID, ABORT_USD = "d3_proof", 0.05


def _keys() -> str:
    return " ".join(f"{n}={'set' if os.getenv(n) else 'unset'}" for n in
                    ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"))


def _show(name: str, report) -> None:
    for v in report.verdicts:
        if isinstance(v, JudgedVerdict):
            print(f"  {name} {v.criterion_id}: A={v.judge_a.verdict} B={v.judge_b.verdict} combined={v.status} "
                  f"flags={list(v.flags)} retriesA={v.judge_a.retries} retriesB={v.judge_b.retries}")


def live(log: str, tsv: str) -> None:
    from agents.baseten_client import BasetenClient
    from agents.meta_client import MetaModelClient

    print(f"mode=live {_keys()}")
    ledger = SpendLedger()
    start = {p: ledger.total_usd(p) for p in ("meta", "baseten")}
    print(f"ledger before: meta=${start['meta']:.8f} baseten=${start['baseten']:.8f}")
    meta, baseten = MetaModelClient(ledger=ledger), BasetenClient(ledger=ledger)
    for task_id, name, text in ANSWERS:
        report = grade_live([(task_id, text)], RUN_ID, log, meta=meta, baseten=baseten)[0]
        _show(name, report)
        DecisionLog(tsv).append(rows_from_grade(report, run_id=RUN_ID, seed=0))
        new = sum(ledger.total_usd(p) - start[p] for p in start)
        if new > ABORT_USD:
            sys.exit(f"ABORT: new spend ${new:.6f} passed ${ABORT_USD}")
    for line in CallLog(log, RUN_ID).read():
        if line["kind"] == "judge":
            print(f"  call seq={line['seq']} judge={line['judge']} model={line['model']} outcome={line['outcome']} "
                  f"in={line['input_tokens']} out={line['output_tokens']} reasoning={line['reasoning_tokens']} "
                  f"cost=${line['cost_usd']:.8f} latency_s={line['latency_s']} reply={line['reply'][:40]!r}")
    end = {p: ledger.total_usd(p) for p in start}
    print(f"ledger after: meta=${end['meta']:.8f} of $40 hard stop, baseten=${end['baseten']:.8f} of $25 guide "
          f"(assumed pricing); new spend meta=${end['meta'] - start['meta']:.8f} "
          f"baseten=${end['baseten'] - start['baseten']:.8f}")


def keyless(log: str, tsv: str) -> None:
    print(f"mode=keyless {_keys()}")
    reports = grade_keyless([(t, x) for t, _, x in ANSWERS], log)
    for (_, name, _), report in zip(ANSWERS, reports):
        _show(name, report)
        DecisionLog(tsv).append(rows_from_grade(report, run_id=RUN_ID, seed=0))
    print(f"replayed {len(CallLog(log, RUN_ID).read())} log lines, every line served")


def compare(first: str, second: str) -> None:
    a, b = DecisionLog(first).read(), DecisionLog(second).read()
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        print(f"  row {i + 1}: {'MATCH' if x == y else 'MISMATCH'} "
              f"{x.task_id + ' ' + x.result if x else None} | {y.task_id + ' ' + y.result if y else None}")
    print(f"rows: live {len(a)}, keyless {len(b)}; all match: {a == b}")
    sys.exit(0 if a == b else 1)


if __name__ == "__main__":
    {"live": live, "keyless": keyless, "compare": compare}[sys.argv[1]](*sys.argv[2:4])
