"""PILOT driver, kept for the record; not for counted runs. Thin run driver (not committed): cycle 0, distill, poison check, causal replay at one repetition. Stops before approval."""
import json, os, sys
from pathlib import Path
REPO = Path(sys.argv[1]); OUT = Path(sys.argv[2]); RID = sys.argv[3]
sys.path.insert(0, str(REPO))
from agents.spend_ledger import SpendLedger
from agents.meta_client import MetaModelClient
from agents.baseten_client import BasetenClient
from pyx.arms import no_memory
from pyx.decisions import DecisionLog, rows_from_grade
from pyx.distill import distill_live
from pyx.grade_run import grade_live
from pyx.lessons import CandidateStore
from pyx.poison_run import run_poison
from pyx.replay import replay_lesson
from pyx.run import grade, metrics, poison_condition, wake
from pyx.worker import worker_client
from pyx.worker_run import work_live

SHA = "2c0d2d3f37949ceb976f2c29c393f6ed4eaee98f09b7ab90c47b6842a8ba1b59"
CAP = {"meta": 0.40, "baseten": 1.75}
OUT.mkdir(parents=True, exist_ok=True)
LOG, ANS, TSV = OUT / "calls.jsonl", OUT / "answers.jsonl", OUT / "decisions.tsv"
print("keys:", " ".join(f"{n}={'set' if os.getenv(n) else 'unset'}" for n in ("MODEL_API_KEY", "BASETEN_API_KEY")))
ledger = SpendLedger()
start = {p: ledger.total_usd(p) for p in CAP}
print(f"ledger before: meta=${start['meta']:.8f} baseten=${start['baseten']:.8f}", flush=True)

def check(step):
    new = {p: ledger.total_usd(p) - start[p] for p in CAP}
    print(f"[{step}] new meta=${new['meta']:.8f} baseten=${new['baseten']:.8f}", flush=True)
    for p in CAP:
        if new[p] > CAP[p]:
            sys.exit(f"ABORT: new {p} spend ${new[p]:.8f} passed ${CAP[p]}")

meta, baseten, worker = MetaModelClient(ledger=ledger), BasetenClient(ledger=ledger), worker_client(ledger=ledger)
ev = dict(eval_path=REPO / "EVAL.md", eval_sha256=SHA)
# cycle 0: no memory on T1 and T2 clean, plus the poison condition, one repetition
answers = wake([("T1", "clean"), ("T2", "clean")], [no_memory()], 1, RID, LOG, ANS, meta=worker, **ev)
check("cycle0 worker")
answers += poison_condition(1, RID, LOG, ANS, meta=worker, **ev)
check("poison condition worker")
reports = []
for a in answers:
    reports += grade([a], LOG, TSV, meta=meta, baseten=baseten)
    check(f"grade {a.task_id} {a.copy}")
m = metrics(answers, reports)
(OUT / "metrics_cycle0.json").write_text(json.dumps(m, indent=2) + "\n")
# distill each answer under its own run id so trace ids match
stores = {"clean": CandidateStore(OUT / "candidates_clean.jsonl"), "planted": CandidateStore(OUT / "candidates_planted.jsonl")}
faults = []
for a, r in zip(answers, reports):
    cands, f = distill_live([(r, a.answer_text)], a.run_id, LOG, meta=meta)
    faults += f
    for c in cands:
        stores[a.copy].append(c)
    check(f"distill {a.task_id} {a.copy}")
print("distill faults:", faults)
# poison check against the copy each candidate came from
for copy, store in stores.items():
    if store.read():
        run_poison(store, f"{RID}_poison_check", 0, copy, DecisionLog(TSV))
passed = {r.lesson_id for r in DecisionLog(TSV).read() if r.step == "poison" and r.result == "pass"}
# causal replay, one repetition: source plus sibling, clean copies
without = {a.task_id: r for a, r in zip(answers, reports) if a.copy == "clean"}
RG = OUT / "replay_grades.tsv"

def run(task_id, ctx, rid):
    got, f = work_live([(task_id, "clean")], rid, 0, ctx.arm, LOG, ANS, meta=worker, context=ctx.text, lesson_ids=ctx.lesson_ids)
    if not got:
        raise RuntimeError(f"replay worker fault {task_id} {rid}: {f}")
    rep = grade_live([(task_id, got[0].answer_text)], rid, LOG, meta=meta, baseten=baseten)[0]
    DecisionLog(RG).append(rows_from_grade(rep, run_id=rid, seed=0, copy="clean"))
    check(f"replay {rid} {task_id}")
    return rep

for copy, store in stores.items():
    for c in store.read():
        if c.lesson.lesson_id in passed:
            DecisionLog(TSV).append([replay_lesson(c, ["T1", "T2"], run, without, f"{RID}_replay", 0, copy)])
end = {p: ledger.total_usd(p) for p in CAP}
print(f"ledger after: meta=${end['meta']:.8f} baseten=${end['baseten']:.8f}; new meta=${end['meta']-start['meta']:.8f} baseten=${end['baseten']-start['baseten']:.8f}")
print("STOP before approval")
