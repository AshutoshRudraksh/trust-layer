"""PR E3 tests: distill over graded reports, recorded live and replayed keylessly."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from agents.meta_client import EmptyReplyError
from pyx.call_log import CallLog, KeyLeakError
from pyx.decisions import DecisionLog
from pyx.distill import META_MODEL, distill_keyless, distill_live, distill_reports, trace_id
from pyx.grade_run import ReplayMismatchError, grade_keyless
from pyx.replay_client import ReplayMissError

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"
NAMES = ("T1_good", "T1_bad", "T2_good", "T2_bad")
ANSWERS = [(n[:2], (FIX / f"{n}.md").read_text()) for n in NAMES]
PAIRS = list(zip(grade_keyless(ANSWERS, FIX / "replay" / "d3_proof.jsonl"), [a for _, a in ANSWERS]))


@dataclass
class _Resp:
    output_text: str
    input_tokens: int = 10
    output_tokens: int = 5
    cost_usd: float = 0.000002


class _Fake:
    def __init__(self, replies=None):
        self.calls, self.replies = [], list(replies or [])

    def respond(self, prompt, **kw):
        self.calls.append((prompt, kw))
        if self.replies:
            r = self.replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return _Resp(r)
        cid = re.search(r"Failed criterion: (\S+)", prompt).group(1)
        return _Resp(f"LESSON: Before answering, find where {cid} looks and quote it.")


def test_t1_bad_gives_four_candidates_each_tied_to_its_trace_and_criterion() -> None:
    fake = _Fake()
    cands, faults = distill_reports([PAIRS[1]], "r1", fake)
    assert len(fake.calls) == 4 and faults == []
    tid = trace_id("r1", "T1", PAIRS[1][1])
    assert [c.lesson.fixes_criterion_id for c in cands] == ["T1.C1", "T1.C3", "T1.C6", "T1.C8"]
    assert {(c.lesson.created_from_trace_id, c.provenance.source_trace_id) for c in cands} == {(tid, tid)}
    assert {(c.lesson.status, c.lesson.version, c.lesson.scope) for c in cands} == {("candidate", 1, "paper_anatomy")}


def test_provenance_is_graded_failure_from_the_model_called() -> None:
    fake = _Fake()
    cands, _ = distill_reports(PAIRS, "r1", fake)
    assert len(cands) == 8
    assert {(c.provenance.source_kind, c.provenance.distiller_model) for c in cands} == {("graded_failure", META_MODEL)}
    assert {c.provenance.source_paper_id for c in cands} == {"2303.11366v4", "2407.01489v2"}
    assert fake.calls[0][1] == {"role": "memory-consolidation", "reasoning_effort": "low",
                                "max_output_tokens": 2048, "temperature": 0}


def test_malformed_reply_gets_one_retry_then_a_fault() -> None:
    fake = _Fake(["no lesson here", "LESSON: Name the table.", "bad", "still bad", EmptyReplyError("empty")])
    cands, faults = distill_reports([PAIRS[1]], "r1", fake)
    assert [c.lesson.fixes_criterion_id for c in cands] == ["T1.C1", "T1.C8"]
    assert [f.split(":")[0] for f in faults] == ["T1.C3", "T1.C6"]
    assert "MALFORMED" in faults[0] and "EmptyReplyError" in faults[1]


def test_distill_writes_no_decisions_rows(monkeypatch) -> None:
    def refuse(*a, **k):
        raise AssertionError("distill is not a verdict step")
    monkeypatch.setattr(DecisionLog, "append", refuse)
    distill_reports(PAIRS, "r1", _Fake())


def test_live_recording_replays_keylessly_with_no_keys(tmp_path, monkeypatch) -> None:
    log = tmp_path / "distill.jsonl"
    live, _ = distill_live(PAIRS, "r1", log, meta=_Fake())
    lines = CallLog(log, "r1").read()
    assert len(lines) == 8 and {(l["kind"], l["judge"]) for l in lines} == {("distill", "D")}
    for name in ("MODEL_API_KEY", "BASETEN_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    keyless, faults = distill_keyless(PAIRS, "r1", log)
    assert keyless == live and faults == []


def test_keyless_miss_and_unused_lines_fail(tmp_path) -> None:
    log = tmp_path / "distill.jsonl"
    distill_live(PAIRS[:2], "r1", log, meta=_Fake())
    with pytest.raises(ReplayMissError):
        distill_keyless(PAIRS, "r1", log)
    with pytest.raises(ReplayMismatchError, match="unused"):
        distill_keyless([PAIRS[0]], "r1", log)


def test_key_screen_refuses_a_reply_with_a_key_value(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "abcdefghijklmnop1234")
    with pytest.raises(KeyLeakError):
        distill_live([PAIRS[1]], "r1", tmp_path / "d.jsonl", meta=_Fake(["LESSON: abcdefghijklmnop1234"]))
