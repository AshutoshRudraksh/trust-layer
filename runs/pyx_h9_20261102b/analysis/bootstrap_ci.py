"""Paired bootstrap 95% CIs for cycle 1 arm differences, from captured cells.

Units are (task, seed) cells, clean copies, paired across arms on the
same cell, exactly the groupings pyx.run.metrics aggregates. A cell's
criterion pass rate is PASS over conclusive (PASS or FAIL) verdicts.
10,000 resamples with replacement, seed 20261103, percentile interval.

Usage: bootstrap_ci.py CELLS_JSON
"""
import json
import random
import sys

rows = json.load(open(sys.argv[1]))
calls, cur = [], []
for r in rows:
    if r == "CALL_BOUNDARY":
        calls.append(cur)
        cur = []
    else:
        cur.append(r)
calls.append(cur)
calls = [c for c in calls if c]

by_arm = {}
for call in calls:
    arms = {r["arm"] for r in call}
    if len(arms) == 1 and len(call) == 6:
        by_arm.setdefault(next(iter(arms)), call)
units = {}
for arm in ("earned_lessons", "free_lessons", "no_memory", "raw_traces"):
    for r in by_arm[arm]:
        if r["copy"] != "clean":
            continue
        conc = [s for _, s in r["verdicts"] if s in ("PASS", "FAIL")]
        if conc:
            units.setdefault((r["task_id"], r["seed"]), {})[arm] = conc.count("PASS") / len(conc)
full = {k: v for k, v in units.items() if len(v) == 4}
print(f"paired units: {len(full)}")
for k in sorted(full):
    print(k, {a: round(v, 4) for a, v in sorted(full[k].items())})
rng = random.Random(20261103)
for other in ("free_lessons", "no_memory", "raw_traces"):
    diffs = [v["earned_lessons"] - v[other] for v in full.values()]
    boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(10000))
    print(f"earned_lessons - {other}: mean {sum(diffs) / len(diffs):+.4f}, "
          f"95% CI [{boots[250]:+.4f}, {boots[9750]:+.4f}]")
