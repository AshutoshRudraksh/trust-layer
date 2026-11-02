"""Pyx F3 proof, $0 and no model call: run the poison check over the 8 E4 candidates, 2 planted and 1 control.

  python3 scripts/pyx_poison_proof.py OUT.tsv

Run f3_clean checks the 8 committed E4 candidates and the control against the
clean texts of their papers. Run f3_planted checks one synthetic candidate per
planted insert against the planted T1 copy. A synthetic planted candidate is
stamped graded_failure, the way a distiller could stamp a lesson that came
through a poisoned answer. The inserts are found here by diffing the two
committed T1 copies; the check itself never sees that diff.
"""
from __future__ import annotations

import difflib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pyx.call_log import _sha256  # noqa: E402
from pyx.decisions import DecisionLog  # noqa: E402
from pyx.lessons import TEXT_CAP, Candidate, CandidateStore, Lesson, Provenance, make_lesson_id  # noqa: E402
from pyx.poison import SPAN_WORDS  # noqa: E402
from pyx.poison_run import run_poison  # noqa: E402

TASKS = ROOT / "pyx" / "tasks"
E4 = ROOT / "evals" / "fixtures" / "pyx" / "replay" / "e4_distill_candidates.jsonl"
T1_ID = "2303.11366v4"
CONTROL = "Before writing, list every table and figure you will cite, then check each claim against one of them."


def planted_inserts() -> list:
    clean = (TASKS / "T1_reflexion_v4.clean.md").read_text(encoding="utf-8").splitlines()
    planted = (TASKS / "T1_reflexion_v4.planted.md").read_text(encoding="utf-8").splitlines()
    found = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, clean, planted, autojunk=False).get_opcodes():
        if op == "insert":
            found.append("\n".join(planted[j1:j2]))
        elif op == "replace":
            old, new = "\n".join(clean[i1:i2]), "\n".join(planted[j1:j2])
            found += [new[y1:y2] for o, _, _, y1, y2 in
                      difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if o in ("insert", "replace")]
    found = [s.strip() for s in found]
    return [s for s in found if len(s.split()) >= SPAN_WORDS and not s.startswith("PLANTED TEST MATERIAL")]


def synthetic(text: str, label: str) -> Candidate:
    text = " ".join(text.split())[:TEXT_CAP]
    lid = make_lesson_id(label, text)
    return Candidate(Lesson(lid, text, "paper_anatomy", "synthetic", label, "candidate", 1),
                     Provenance(lid, "synthetic", T1_ID, "graded_failure", "none", _sha256(text)))


def run_proof(out: Path):
    log = DecisionLog(out)
    with tempfile.TemporaryDirectory() as tmp:
        clean, planted = CandidateStore(Path(tmp) / "clean.jsonl"), CandidateStore(Path(tmp) / "planted.jsonl")
        for c in CandidateStore(E4).read() + [synthetic(CONTROL, "SYNTH_CONTROL")]:
            clean.append(c)
        for label, text in zip(("SYNTH_PLANTED_A", "SYNTH_PLANTED_B"), planted_inserts()):
            planted.append(synthetic(text, label))
        verdicts = run_poison(clean, run_id="f3_clean", seed=0, copy="clean", log=log)
        verdicts += run_poison(planted, run_id="f3_planted", seed=0, copy="planted", log=log)
        rows_before = len(log.read())
        run_poison(clean, run_id="f3_clean", seed=0, copy="clean", log=log)
        run_poison(planted, run_id="f3_planted", seed=0, copy="planted", log=log)
        return verdicts, len(log.read()) - rows_before


if __name__ == "__main__":
    verdicts, added = run_proof(Path(sys.argv[1]))
    for v in verdicts:
        print(f"  {v.lesson_id} passed={v.passed} reason_code={v.reason_code or '-'} rule={v.rule or '-'} "
              f"detail={v.detail!r}")
    print(f"verdicts={len(verdicts)} failed={sum(not v.passed for v in verdicts)} rows added on rerun={added}")
