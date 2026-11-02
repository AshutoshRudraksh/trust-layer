"""Pyx E4 proof: distill the eight failed criteria of the D3 proof live with recording, then replay keylessly.

  python3 scripts/pyx_distill_proof.py live LOG OUT      live Meta calls, needs MODEL_API_KEY
  python3 scripts/pyx_distill_proof.py keyless LOG OUT   no key, no network: replays LOG
  python3 scripts/pyx_distill_proof.py compare OUT OUT   candidate by candidate comparison

The graded reports come from a keyless replay of the committed D3 proof log, so
grading costs $0. Prints only whether each key name is set, never a value. The
live mode stops after any answer once new Meta spend passes $0.02.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents.spend_ledger import SpendLedger  # noqa: E402
from pyx.call_log import CallLog  # noqa: E402
from pyx.distill import distill_keyless, distill_live  # noqa: E402
from pyx.grade_run import grade_keyless  # noqa: E402
from pyx.lessons import CandidateStore  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "evals" / "fixtures" / "pyx"
NAMES = ("T1_good", "T1_bad", "T2_good", "T2_bad")
ANSWERS = [(n[:2], (FIX / f"{n}.md").read_text()) for n in NAMES]
RUN_ID, ABORT_USD = "e4_proof", 0.02


def _keys() -> str:
    return " ".join(f"{n}={'set' if os.getenv(n) else 'unset'}" for n in
                    ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"))


def _pairs():
    return list(zip(grade_keyless(ANSWERS, FIX / "replay" / "d3_proof.jsonl"), [a for _, a in ANSWERS]))


def _show(candidates, faults, out: str) -> None:
    store = CandidateStore(out)
    for c in candidates:
        store.append(c)
        print(f"  {c.lesson.lesson_id} fixes={c.lesson.fixes_criterion_id} paper={c.provenance.source_paper_id} "
              f"kind={c.provenance.source_kind} model={c.provenance.distiller_model} "
              f"trace={c.lesson.created_from_trace_id[:12]}")
        print(f"    text: {c.lesson.text}")
    for f in faults:
        print(f"  FAULT {f}")
    print(f"candidates={len(candidates)} faults={len(faults)}")


def live(log: str, out: str) -> None:
    from agents.meta_client import MetaModelClient

    print(f"mode=live {_keys()}")
    ledger = SpendLedger()
    start = {p: ledger.total_usd(p) for p in ("meta", "baseten")}
    print(f"ledger before: meta=${start['meta']:.8f} baseten=${start['baseten']:.8f}")
    meta = MetaModelClient(ledger=ledger)
    candidates, faults = [], []
    for pair in _pairs():
        c, f = distill_live([pair], RUN_ID, log, meta=meta)
        candidates, faults = candidates + c, faults + f
        new = ledger.total_usd("meta") - start["meta"]
        if new > ABORT_USD:
            sys.exit(f"ABORT: new Meta spend ${new:.8f} passed ${ABORT_USD}")
    for line in CallLog(log, RUN_ID).read():
        print(f"  call seq={line['seq']} kind={line['kind']} model={line['model']} outcome={line['outcome']} "
              f"in={line['input_tokens']} out={line['output_tokens']} reasoning={line['reasoning_tokens']} "
              f"cost=${line['cost_usd']:.8f} latency_s={line['latency_s']}")
    _show(candidates, faults, out)
    end = {p: ledger.total_usd(p) for p in start}
    print(f"ledger after: meta=${end['meta']:.8f} of $40 hard stop, baseten=${end['baseten']:.8f} of $25 guide; "
          f"new spend meta=${end['meta'] - start['meta']:.8f} baseten=${end['baseten'] - start['baseten']:.8f}")


def keyless(log: str, out: str) -> None:
    print(f"mode=keyless {_keys()}")
    candidates, faults = distill_keyless(_pairs(), RUN_ID, log)
    _show(candidates, faults, out)
    print(f"replayed {len(CallLog(log, RUN_ID).read())} log lines, every line served")


def compare(first: str, second: str) -> None:
    a, b = CandidateStore(first).read(), CandidateStore(second).read()
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        print(f"  candidate {i + 1}: {'MATCH' if x == y else 'MISMATCH'} "
              f"{x.lesson.lesson_id if x else None} | {y.lesson.lesson_id if y else None}")
    same = Path(first).read_bytes() == Path(second).read_bytes()
    print(f"candidates: live {len(a)}, keyless {len(b)}; all match: {a == b}; files byte identical: {same}")
    sys.exit(0 if a == b and same else 1)


if __name__ == "__main__":
    {"live": live, "keyless": keyless, "compare": compare}[sys.argv[1]](*sys.argv[2:4])
