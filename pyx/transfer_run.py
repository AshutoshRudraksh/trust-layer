"""Held out transfer run (ticket 4; docs/proposals/held-out-transfer-task.md, approved by Muse Nov 13, 2026).

One held out paper (H2), two arms (no_memory and earned_lessons), 5 paired repetitions, so 10 worker
answers. Each answer is graded against the frozen H2 rubric: programmatic criteria by check_answer,
judged criteria by Judge A (Meta) and Judge B (Baseten) through judge_criterion.

Refusals come in a fixed order, before any file is written or any call is made:
1. the rubric file's sha256 must equal docs/proposals/held-out-rubric.sha256;
2. a live run needs MODEL_API_KEY and BASETEN_API_KEY, both non empty;
3. no client may be in the Meta client's keyless local fallback (dry_run). NoFallback refuses a keyless
   client at construction and raises FallbackRefused on any dry_run reply before it can be logged, so a
   fake run is never recorded as real;
4. a live run from the CLI probes Judge A and Judge B once each (PROBE_PROMPT) before any worker call. The probe
   is kept out of calls.jsonl and spend.json (its cost lands in the shared ledger only); run_meta.json records
   the probe verdicts and which Judge B graded the run. Judge B is set with --judge-b provider:model.

Spend: budget_start.json holds each provider's shared ledger total at start; spend.json is rewritten
after every call with the new spend per provider (ledger delta for a live run, the logged cost for a
keyless replay). A call that takes new Meta spend past CAPS["meta"], new Baseten spend past
CAPS["baseten"], or the two together past HARD_STOP_USD aborts the run with abort.txt, and so does a
non retryable provider HTTP error (provider, status and message in abort.txt). The check runs
after each call, so the overshoot is at most one call's cost. The $40 combined envelope covers spend
from earlier runs tonight too, which this script cannot see; the operator checks it from the shared
ledger before starting.

A keyless replay (live=None, src_log=<run>/calls.jsonl) serves every call from the log, needs no key,
uses the recorded Judge B, refuses if the paper differs from the recorded paper, and fails if any logged call is left unserved.
The rubric copy is published into the run dir only after a run completes. There is no resume: an
aborted run is restarted into a new directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pyx.checker import PENDING_JUDGE, check_answer
from pyx.judges import judge_criterion

ROOT = Path(__file__).resolve().parent.parent
RUBRIC_SHA256_FILE = ROOT / "docs" / "proposals" / "held-out-rubric.sha256"
COUNTED_RUN = ROOT / "runs" / "pyx_h9_20261102b"  # read only
EARNED_LESSON_ID = "L_T1.C8_79e93c16"
EARNED_LESSON_SHA256 = "79e93c169ff6d8ae142cab2a2f4c2c229e118714e07e9aefce182a415e5a928d"
TASK_ID = "H2"
COPY = "transfer"
ARMS = ("no_memory", "earned_lessons")
REPS = 5
CAPS = {"meta": 3.0, "baseten": 5.0}  # new spend in USD per provider (proposal, section 7)
HARD_STOP_USD = 25.0  # new spend in USD, both providers together
KEY_NAMES = ("MODEL_API_KEY", "BASETEN_API_KEY")


class RefuseToStart(RuntimeError):
    """The run must not start: wrong rubric, a missing key, a fallback client, or a changed paper."""


class FallbackRefused(RuntimeError):
    """A client answered from the keyless local fallback (dry_run). The reply is never logged."""


class TransferAbort(RuntimeError):
    """A spend cap or the hard stop was crossed, or a provider refused a call."""


@dataclass(frozen=True)
class JudgeB:
    provider: str  # "baseten" or "meta"; also the spend provider its calls are metered under
    model: str
    endpoint: str  # "chat_completions" (Baseten) or "responses" (Meta Model API)


# Pre-registered Judge B. Its Baseten version (wpgy40e) was retired on Nov 13, 2026; see the amendment in
# docs/proposals/held-out-transfer-task.md. It stays the default so an unconfigured run is refused by preflight.
JUDGE_B_PREREGISTERED = JudgeB("baseten", "meta-models/muse-spark-open-1026", "chat_completions")
JUDGE_B_ENDPOINTS = {"baseten": "chat_completions", "meta": "responses"}
PROBE_PROMPT = ("Liveness check before a graded run; this is not a graded criterion. "
                "Reply with exactly one word: PASS or FAIL. Reply PASS.")


def parse_judge_b(spec: str) -> JudgeB:
    """provider:model, for example baseten:meta-models/muse-spark-open or meta:muse-spark-1.3."""
    from pyx.grade_run import META_MODEL
    from pyx.worker import WORKER_MODEL
    provider, sep, model = spec.partition(":")
    if not sep or provider not in JUDGE_B_ENDPOINTS or not model.strip():
        raise RefuseToStart(f"Judge B {spec!r}: provider must be one of {sorted(JUDGE_B_ENDPOINTS)}, as provider:model")
    if "llama" in model.lower():
        raise RefuseToStart(f"Judge B {model!r}: Llama models are not allowed (Muse ruling, Meta Muse models only)")
    if provider == "meta" and model in (META_MODEL, WORKER_MODEL):
        raise RefuseToStart(f"Judge B {model!r} must be distinct from Judge A and the worker")
    return JudgeB(provider, model, JUDGE_B_ENDPOINTS[provider])


class MetaChatJudge:
    """A Judge B on the Meta Model API: judges.py calls chat(), this answers through respond() with its model."""

    def __init__(self, inner: Any, model: str) -> None:
        self._inner, self._model = inner, model

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def chat(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> Any:
        return self._inner.respond(prompt, role="eval-runner", model=self._model, reasoning_effort="low",
                                   max_output_tokens=max_tokens, temperature=temperature)


def _describe(exc: BaseException) -> str:
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}: {' '.join(exc.response.text.split())[:500]}"
    return f"{type(exc).__name__}: {exc}"


def preflight(a: Any, b: Any) -> Dict[str, str]:
    """Probe both judges once with the judge call shape. Not logged in the run; costs land in the ledger only."""
    from pyx.judges import _ask, parse_reply
    result = {}
    for judge, client in (("A", a), ("B", b)):
        try:
            reply = _ask(judge, client, PROBE_PROMPT).output_text
        except Exception as exc:  # any failure means this judge cannot grade tonight
            raise RefuseToStart(f"preflight: Judge {judge} did not answer: {_describe(exc)}") from exc
        verdict = parse_reply(reply)
        if verdict is None:
            raise RefuseToStart(f"preflight: Judge {judge} replied {reply[:80]!r}, not PASS or FAIL")
        result[judge] = verdict
    return result


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def committed_rubric_sha256() -> str:
    return RUBRIC_SHA256_FILE.read_text(encoding="utf-8").strip()


def verify_rubric(path: Any, expected_sha256: Optional[str] = None) -> Dict[str, Any]:
    expected = expected_sha256 or committed_rubric_sha256()
    data = Path(path).read_bytes()
    actual = _sha256_bytes(data)
    if actual != expected:
        raise RefuseToStart(f"rubric sha256 {actual} does not match the committed sha256 {expected}")
    return json.loads(data.decode("utf-8"))


def require_live_keys(env: Mapping[str, str]) -> None:
    missing = [name for name in KEY_NAMES if not str(env.get(name, "")).strip()]
    if missing:
        raise RefuseToStart(f"a live run needs {' and '.join(missing)}; refusing so no fallback run is recorded")


class NoFallback:
    """Wraps a live client. Refuses a keyless client up front and any dry_run reply afterwards."""

    def __init__(self, inner: Any) -> None:
        if hasattr(inner, "api_key") and not str(inner.api_key or "").strip():
            raise RefuseToStart(f"{type(inner).__name__} has no API key and would use the local fallback")
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _check(self, resp: Any) -> Any:
        if getattr(resp, "dry_run", False):
            raise FallbackRefused(f"{type(self._inner).__name__} returned a dry_run reply; nothing was logged")
        return resp

    def respond(self, prompt: str, **kwargs: Any) -> Any:
        return self._check(self._inner.respond(prompt, **kwargs))

    def chat(self, prompt: str, **kwargs: Any) -> Any:
        return self._check(self._inner.chat(prompt, **kwargs))


@dataclass(frozen=True)
class EarnedContext:
    arm: str
    text: str
    lesson_ids: Tuple[str, ...]


def earned_context(run_dir: Path = COUNTED_RUN) -> EarnedContext:
    """The earned lessons arm exactly as the counted run built it, read only from its files."""
    from pyx.arms import earned_lessons
    from pyx.decisions import DecisionLog
    from pyx.lessons import CandidateStore
    ctx = earned_lessons(CandidateStore(run_dir / "candidates_r0.jsonl").read(),
                         DecisionLog(run_dir / "decisions.tsv").read())
    if ctx.lesson_ids != (EARNED_LESSON_ID,):
        raise RefuseToStart(f"earned lessons are {ctx.lesson_ids}, expected only {EARNED_LESSON_ID}")
    text = ctx.text.split(": ", 1)[1]
    if _sha256_bytes(text.encode("utf-8")) != EARNED_LESSON_SHA256:
        raise RefuseToStart(f"lesson {EARNED_LESSON_ID} text does not match its sha256")
    return EarnedContext(ctx.arm, ctx.text, ctx.lesson_ids)


class Spend:
    """New spend per provider, written to spend.json after every call and checked against the caps."""

    def __init__(self, out: Path, ledger: Any, caps: Mapping[str, float], hard_stop_usd: float) -> None:
        self.out, self.ledger, self.caps, self.hard_stop = out, ledger, dict(caps), hard_stop_usd
        self.start = {p: (ledger.total_usd(p) if ledger is not None else 0.0) for p in self.caps}
        self.logged = {p: 0.0 for p in self.caps}
        (out / "budget_start.json").write_text(json.dumps(
            {"ledger_total_usd": self.start, "caps_usd": self.caps, "hard_stop_usd": hard_stop_usd},
            indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.write()

    def delta(self, provider: str) -> float:
        if self.ledger is None:
            return round(self.logged[provider], 8)
        return round(self.ledger.total_usd(provider) - self.start[provider], 8)

    def write(self) -> None:
        body = {p: {"run_delta": self.delta(p), "logged_cost_usd": round(self.logged[p], 8), "cap_usd": self.caps[p]}
                for p in self.caps}
        (self.out / "spend.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def after_call(self, provider: str, cost: float) -> None:
        self.logged[provider] += float(cost or 0.0)
        self.write()
        for p in self.caps:
            if self.delta(p) > self.caps[p]:
                self._abort(f"new {p} spend ${self.delta(p):.4f} is past the ${self.caps[p]:.2f} cap")
        total = sum(self.delta(p) for p in self.caps)
        if total > self.hard_stop:
            self._abort(f"new spend ${total:.4f} on both providers is past the ${self.hard_stop:.2f} hard stop")

    def _abort(self, reason: str) -> None:
        (self.out / "abort.txt").write_text(f"ABORT: {reason}\n", encoding="utf-8")
        raise TransferAbort(reason)


class Metered:
    """Outermost wrapper: after each call (already logged below it), counts spend and checks the caps."""

    def __init__(self, inner: Any, provider: str, spend: Spend) -> None:
        self._inner, self._provider, self._spend = inner, provider, spend

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _call(self, method: str, prompt: str, **kwargs: Any) -> Any:
        import httpx
        try:
            resp = getattr(self._inner, method)(prompt, **kwargs)
        except httpx.HTTPStatusError as exc:  # non retryable (for example 400 deactivated); 429 is retried below us
            self._spend.write()
            self._spend._abort(f"{self._provider} {_describe(exc)}")
        self._spend.after_call(self._provider, resp.cost_usd)
        return resp

    def respond(self, prompt: str, **kwargs: Any) -> Any:
        return self._call("respond", prompt, **kwargs)

    def chat(self, prompt: str, **kwargs: Any) -> Any:
        return self._call("chat", prompt, **kwargs)


# role: (log judge name, model, endpoint, log kind, provider)
def _spec(judge_b: JudgeB) -> Dict[str, Tuple[str, str, str, str, str]]:
    from pyx.grade_run import META_MODEL
    from pyx.worker import WORKER_MODEL
    return {"worker": ("W", WORKER_MODEL, "responses", "worker", "meta"),
            "a": ("A", META_MODEL, "responses", "judge", "meta"),
            "b": ("B", judge_b.model, judge_b.endpoint, "judge", judge_b.provider)}


def _grade(answer: str, rubric: Dict[str, Any], a: Any, b: Any) -> List[Tuple[str, str, str, str, str, str]]:
    by_id = {c["id"]: c for c in rubric["criteria"]}
    rows = []
    for v in check_answer(answer, rubric):
        if v.status != PENDING_JUDGE:
            rows.append((v.criterion_id, v.status, v.check, "", "", ""))
            continue
        j = judge_criterion(by_id[v.criterion_id], answer, a, b)
        rows.append((j.criterion_id, j.status, j.check, j.judge_a.verdict, j.judge_b.verdict, ",".join(j.flags)))
    return rows


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def run_transfer(out: Any, rubric_path: Any, paper_path: Any, live: Optional[Dict[str, Any]], ledger: Any,
                 env: Optional[Mapping[str, str]] = None, src_log: Any = None,
                 expected_sha256: Optional[str] = None, caps: Optional[Mapping[str, float]] = None,
                 hard_stop_usd: Optional[float] = None, judge_b: Optional[JudgeB] = None,
                 probe: bool = False) -> Dict[str, Any]:
    from pyx.call_log import CallLog
    from pyx.recording import RecordingClient
    from pyx.replay_client import ReplayClient
    from pyx.worker import build_worker_prompt
    from pyx.worker_run import _ask

    rubric = verify_rubric(rubric_path, expected_sha256)  # 1. before anything else
    rubric_sha = _sha256_bytes(Path(rubric_path).read_bytes())
    env = os.environ if env is None else env
    keyless = live is None
    if keyless:
        if src_log is None:
            raise RefuseToStart("a keyless replay needs src_log, the calls.jsonl of a recorded run")
    else:
        require_live_keys(env)  # 2.
        guarded = {role: NoFallback(client) for role, client in live.items()}  # 3.
    paper = Path(paper_path).read_text(encoding="utf-8")
    paper_sha = _sha256_bytes(paper.encode("utf-8"))
    if keyless:
        src_meta = json.loads((Path(src_log).parent / "run_meta.json").read_text(encoding="utf-8"))
        if src_meta["paper_sha256"] != paper_sha or src_meta["rubric_sha256"] != rubric_sha:
            raise RefuseToStart("keyless replay: the paper or rubric differs from the recorded run")
        judge_b = JudgeB(**src_meta["judge_b"]) if "judge_b" in src_meta else JUDGE_B_PREREGISTERED
    judge_b = judge_b or JUDGE_B_PREREGISTERED
    earned = earned_context()
    probed = preflight(guarded["a"], guarded["b"]) if probe and not keyless else None  # before any worker call

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    run_id = out.name
    (out / "run_meta.json").write_text(json.dumps({
        "run_id": run_id, "task_id": TASK_ID, "mode": "keyless_replay" if keyless else "live",
        "rubric_sha256": rubric_sha, "paper_sha256": paper_sha, "arms": list(ARMS), "reps": REPS,
        "earned_lesson_ids": list(earned.lesson_ids), "earned_lesson_sha256": EARNED_LESSON_SHA256,
        "source_log": str(src_log) if keyless else "",
        "judge_b": {"provider": judge_b.provider, "model": judge_b.model, "endpoint": judge_b.endpoint},
        "preflight": probed}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    spend = Spend(out, ledger, caps or CAPS, HARD_STOP_USD if hard_stop_usd is None else hard_stop_usd)

    log = CallLog(out / "calls.jsonl", run_id)
    clients: Dict[str, Any] = {}
    replays: List[Any] = []
    lines = [] if not keyless else CallLog(Path(src_log), run_id).read()
    for role, (judge, model, endpoint, kind, provider) in _spec(judge_b).items():
        if keyless:
            inner = ReplayClient(lines, judge, kind, fallback=False)
            replays.append(inner)
        else:
            inner = guarded[role]
        recorded = RecordingClient(inner, log, judge=judge, model=model, endpoint=endpoint,
                                   held_out=(kind == "judge"), kind=kind)
        clients[role] = Metered(recorded, provider, spend)

    contexts = {"no_memory": "", "earned_lessons": earned.text}
    rows: List[str] = []
    answers = out / "answers.jsonl"
    for rep in range(REPS):
        for arm in ARMS:
            prompt = build_worker_prompt(TASK_ID, COPY, contexts[arm], text=paper)
            text, fault = _ask(prompt, clients["worker"])
            graded = _grade(text, rubric, clients["a"], clients["b"]) if text is not None else []
            _append_jsonl(answers, {"rep": rep, "arm": arm, "answer": text, "fault": fault,
                                    "answer_sha256": _sha256_bytes(text.encode("utf-8")) if text else "",
                                    "verdicts": [[cid, status] for cid, status, *_ in graded]})
            rows += ["\t".join([str(rep), arm, *map(str, g)]) for g in graded]
            if text is None:
                rows.append("\t".join([str(rep), arm, "*", "NO_ANSWER", "", "", "", fault]))

    if keyless:
        left = sum(len(r.unused()) for r in replays)
        if left:
            raise RefuseToStart(f"keyless replay left {left} logged calls unserved; the replay did not match")
    header = "rep\tarm\tcriterion_id\tstatus\tcheck\tjudge_a\tjudge_b\tflags\n"
    (out / "verdicts.tsv").write_text(header + "".join(r + "\n" for r in rows), encoding="utf-8")
    (out / "rubric.json").write_bytes(Path(rubric_path).read_bytes())
    return {"answers": REPS * len(ARMS), "spend": {p: spend.delta(p) for p in spend.caps}}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pyx.transfer_run", description=__doc__.split("\n")[0])
    parser.add_argument("--rubric", required=True, help="path to the frozen H2 rubric JSON (kept out of the repo)")
    parser.add_argument("--paper", required=True, help="path to the H2 paper text (arXiv 2405.15793v3)")
    parser.add_argument("--out", required=True, help="new run directory, for example runs/pyx_transfer_h2_20261113")
    parser.add_argument("--keyless", action="store_true", help="replay from --from with no key and no network")
    parser.add_argument("--from", dest="src", help="recorded run directory for --keyless")
    parser.add_argument("--judge-b", help="provider:model for Judge B, for example baseten:meta-models/muse-spark-open; "
                                          "defaults to the pre-registered (retired) Judge B; keyless uses the recorded one")
    args = parser.parse_args(argv)
    try:
        verify_rubric(args.rubric)  # first, before the ledger or keys are looked at
        if args.keyless:
            if not args.src:
                raise RefuseToStart("--keyless needs --from <recorded run dir>")
            summary = run_transfer(args.out, args.rubric, args.paper, None, None,
                                   src_log=Path(args.src) / "calls.jsonl")
        else:
            require_live_keys(os.environ)
            ledger_file = os.environ.get("PYX_SPEND_LEDGER", "")
            if not ledger_file or not Path(ledger_file).is_file():
                raise RefuseToStart("a live run needs PYX_SPEND_LEDGER naming an existing shared ledger file")
            from agents.baseten_client import BasetenClient
            from agents.meta_client import MetaModelClient
            from agents.spend_ledger import SpendLedger
            from pyx.worker import worker_client
            judge_b = parse_judge_b(args.judge_b) if args.judge_b else JUDGE_B_PREREGISTERED
            ledger = SpendLedger()
            b = (BasetenClient(model=judge_b.model, ledger=ledger) if judge_b.provider == "baseten"
                 else MetaChatJudge(MetaModelClient(ledger=ledger), judge_b.model))
            live = {"worker": worker_client(ledger=ledger), "a": MetaModelClient(ledger=ledger), "b": b}
            summary = run_transfer(args.out, args.rubric, args.paper, live, ledger, judge_b=judge_b, probe=True)
    except (RefuseToStart, FallbackRefused, TransferAbort) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
