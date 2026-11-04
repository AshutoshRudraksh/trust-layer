"""Capture per answer criterion verdicts from the pipeline's own metrics calls.

Runs both phases keyless against a committed run record while wrapping
pyx.phase.metrics, the protocol's own aggregation function, and writes
every answer it grades (arm, task, copy, seed, per criterion statuses)
to a JSON file. Nothing is recomputed outside the pipeline.

Usage: capture_cells.py RUN_DIR OUT_DIR CELLS_JSON
RUN_DIR holds the record being reproduced (its calls.jsonl is the log).
"""
import json
import shutil
import sys
from pathlib import Path

import pyx.phase as phase


def main() -> int:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    cells_path = Path(sys.argv[3])
    eval_sha = "73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb"
    run_id = src.name
    captured = []
    orig = phase.metrics

    def wrapped(answers, reports):
        captured.append("CALL_BOUNDARY")
        for a, r in zip(answers, reports):
            captured.append({
                "arm": a.arm, "task_id": a.task_id, "copy": a.copy,
                "seed": getattr(a, "seed", None),
                "verdicts": [[v.criterion_id, v.status] for v in r.verdicts],
            })
        return orig(answers, reports)

    phase.metrics = wrapped
    if out.exists():
        shutil.rmtree(out)
    log = src / "calls.jsonl"
    code = phase.phase1(out, run_id, eval_sha, 3, None, None, None, log)
    if code == 0:
        code = phase.phase1(out, run_id, eval_sha, 3, src / "pairs.txt", None, None, log)
    if code == 0:
        approval = [l for l in (src / "decisions.tsv").read_text().splitlines()
                    if "\tapproval\t" in l]
        with open(out / "decisions.tsv", "a") as fh:
            fh.write("\n".join(approval) + "\n")
        captured.clear()
        code = phase.phase2(out, run_id, eval_sha, 3, None, None, log)
    cells_path.write_text(json.dumps(captured))
    print(f"phase codes end at {code}; captured entries: {len(captured)}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
