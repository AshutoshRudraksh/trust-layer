"""Step 1 ticket 1: the consumer read path never serves unadmitted lesson text.

A consumer agent reads the bank only through the MCP tools. Only a lesson the
bank calls earned (poison pass, replay pass, HUMAN_APPROVED) may reach it with
its text. Every other candidate, including the planted source candidates the
replay rejected, comes back as its sha256 and verdict rows, never its text.
Spec: docs/specs/step1-consumer-agent.md, ticket 1.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pyx.bank import LessonBank
from pyx.lessons import CandidateStore

REPO = Path(__file__).resolve().parents[1]
COUNTED_RUN = REPO / "runs" / "pyx_h9_20261102b"
ADMITTED = "L_T1.C8_79e93c16"
PLANTED = ["L_T1.C1_9dd514bb", "L_T1.C4_f8095214", "L_T1.C8_09e61a71"]


def _texts() -> dict:
    texts = {}
    for path in COUNTED_RUN.glob("candidates*.jsonl"):
        for c in CandidateStore(path).read():
            texts[c.lesson.lesson_id] = c.lesson.text
    return texts


def _call_provenance(bank: LessonBank, lesson_id: str) -> str:
    from pyx.mcp_server import build_server
    out = asyncio.run(build_server(bank).call_tool("get_lesson_provenance", {"lesson_id": lesson_id}))
    blocks = out[0] if isinstance(out, tuple) else out
    return "".join(b.text for b in blocks)


def test_bank_withholds_text_of_every_unadmitted_candidate() -> None:
    bank = LessonBank.load(COUNTED_RUN)
    texts = _texts()
    unadmitted = sorted(set(texts) - {ADMITTED})
    rep0 = {c.lesson.lesson_id for c in CandidateStore(COUNTED_RUN / "candidates_r0.jsonl").read()}
    assert (len(rep0), len(texts), len(unadmitted)) == (11, 35, 34)
    assert set(PLANTED) <= set(unadmitted) and ADMITTED in rep0
    for lid in unadmitted:
        record = bank.provenance(lid)
        assert record["earned"] is False
        assert "text" not in record
        assert texts[lid] not in json.dumps(record)
        assert record["text_sha256"].startswith(lid.rsplit("_", 1)[1])
        assert bool(record["decisions"]) == (lid in rep0), lid


def test_bank_still_serves_the_admitted_lesson_text() -> None:
    record = LessonBank.load(COUNTED_RUN).provenance(ADMITTED)
    assert record["earned"] is True
    assert record["text"] == _texts()[ADMITTED]


@pytest.mark.parametrize("lesson_id", PLANTED)
def test_mcp_provenance_tool_never_returns_planted_text(lesson_id: str) -> None:
    pytest.importorskip("mcp")
    served = _call_provenance(LessonBank.load(COUNTED_RUN), lesson_id)
    record = json.loads(served)
    assert _texts()[lesson_id] not in served
    assert (record["lesson_id"], record["earned"], "text" in record) == (lesson_id, False, False)
    assert [d["result"] for d in record["decisions"] if d["step"] == "replay"] == ["fail"]
