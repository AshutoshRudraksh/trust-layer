"""PILOT driver, kept for the record; not for counted runs. Keyless rerun of a thin pilot run (not counted): serves every worker, judge and distill call from calls.jsonl.
No key is read and socket connect is blocked. Writes a fresh directory to compare byte for byte."""
import os, socket, sys
from pathlib import Path


def _refuse(*a, **k):
    raise RuntimeError("network blocked in keyless rerun")


socket.socket.connect = _refuse
for n in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
    os.environ.pop(n, None)
REPO, SRC, OUT, RID = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
sys.path.insert(0, str(REPO))
from pyx.arms import no_memory
from pyx.call_log import CallLog
from pyx.decisions import DecisionLog, rows_from_grade
from pyx.distill import distill_reports
from pyx.grade_run import ReplayMismatchError, _check_against_log
from pyx.judges import grade_answer
from pyx.lessons import CandidateStore
from pyx.poison_run import run_poison
from pyx.replay import replay_lesson
from pyx.replay_client import ReplayClient
from pyx.worker_run import AnswerStore, work

OUT.mkdir(parents=True, exist_ok=True)
lines = CallLog(SRC / "calls.jsonl", "").read()
W = ReplayClient(lines, judge="W", kind="worker")
D = ReplayClient(lines, judge="D", kind="distill")
A, B = ReplayClient(lines, judge="A"), ReplayClient(lines, judge="B")
checker = iter([l for l in lines if l["kind"] == "checker"])
ANS, TSV, RG = AnswerStore(OUT / "answers.jsonl"), DecisionLog(OUT / "decisions.tsv"), DecisionLog(OUT / "replay_grades.tsv")


def grade(task_id, text):
    _check_against_log(task_id, text, next(checker))
    return grade_answer(text, task_id, A, B)


ctx = no_memory()
answers = work([("T1", "clean"), ("T2", "clean")], f"{RID}_r0", 0, ctx.arm, W, ANS)[0]
answers += work([("T1", "planted")], f"{RID}_poison_r0", 0, ctx.arm, W, ANS)[0]
reports = []
for a in answers:
    r = grade(a.task_id, a.answer_text)
    TSV.append(rows_from_grade(r, run_id=a.run_id, seed=a.seed, copy=a.copy))
    reports.append(r)
stores = {"clean": CandidateStore(OUT / "candidates_clean.jsonl"), "planted": CandidateStore(OUT / "candidates_planted.jsonl")}
for a, r in zip(answers, reports):
    for c in distill_reports([(r, a.answer_text)], a.run_id, D)[0]:
        stores[a.copy].append(c)
for copy, store in stores.items():
    if store.read():
        run_poison(store, f"{RID}_poison_check", 0, copy, TSV)
passed = {r.lesson_id for r in TSV.read() if r.step == "poison" and r.result == "pass"}
without = {a.task_id: r for a, r in zip(answers, reports) if a.copy == "clean"}


def run(task_id, c, rid):
    got = work([(task_id, "clean")], rid, 0, c.arm, W, ANS, context=c.text, lesson_ids=c.lesson_ids)[0]
    rep = grade(task_id, got[0].answer_text)
    RG.append(rows_from_grade(rep, run_id=rid, seed=0, copy="clean"))
    return rep


for copy, store in stores.items():
    for c in store.read():
        if c.lesson.lesson_id in passed:
            TSV.append([replay_lesson(c, ["T1", "T2"], run, without, f"{RID}_replay", 0, copy)])
left = {n: len(cl.unused()) for n, cl in (("worker", W), ("distill", D), ("A", A), ("B", B))}
left["checker"] = sum(1 for _ in checker)
print("unused log lines:", left)
if any(left.values()):
    raise ReplayMismatchError(f"unused lines {left}")
