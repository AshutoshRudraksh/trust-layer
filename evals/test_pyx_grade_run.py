"""PR D3b tests: grade_live records, grade_keyless replays and checks. Fake inner clients, no network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.meta_client import EmptyReplyError
from pyx import grade_run
from pyx.call_log import CallLog
from pyx.grade_run import ReplayMismatchError, grade_keyless, grade_live
from pyx.judges import INCONCLUSIVE, JUDGE_DISAGREE, JudgedVerdict

FIX = Path(__file__).resolve().parent / "fixtures" / "pyx"
ANSWERS = [(f[:2], (FIX / f"{f}.md").read_text()) for f in ("T1_good", "T1_bad", "T2_good", "T2_bad")]


class _Reply:
    def __init__(self, text: str) -> None:
        self.output_text, self.input_tokens, self.output_tokens, self.cost_usd = text, 10, 5, 0.001


class _Fake:
    def __init__(self, script):
        self.script = list(script)

    def _next(self, prompt, **kw):
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Reply(item)

    respond = chat = _next


def _live(tmp_path: Path):
    # T1_good split, T1_bad both FAIL, T2_good A errors (INCONCLUSIVE), T2_bad both FAIL
    meta = _Fake(["FAIL", "FAIL", EmptyReplyError("no final text"), "FAIL"])
    base = _Fake(["PASS", "FAIL", "PASS", "maybe", "FAIL"])
    path = tmp_path / "proof.jsonl"
    return path, grade_live(ANSWERS, "run1", path, meta=meta, baseten=base)


def _judged(reports):
    return [(v.status, v.flags, v.judge_a.verdict, v.judge_b.verdict) for r in reports
            for v in r.verdicts if isinstance(v, JudgedVerdict)]


def test_live_writes_a_checker_line_before_each_answers_judge_lines(tmp_path: Path) -> None:
    path, _ = _live(tmp_path)
    kinds = [l["kind"] for l in CallLog(path, "run1").read()]
    assert kinds[0] == "checker" and kinds.count("checker") == 4
    assert kinds == ["checker", "judge", "judge"] * 3 + ["checker", "judge", "judge", "judge"]


def test_keyless_reproduces_pass_fail_split_and_inconclusive(tmp_path: Path, monkeypatch) -> None:
    path, live = _live(tmp_path)

    def refuse(*a, **k):
        raise AssertionError("keyless mode must not build a real client")

    monkeypatch.setattr(grade_run, "MetaModelClient", refuse)
    monkeypatch.setattr(grade_run, "BasetenClient", refuse)
    keyless = grade_keyless(ANSWERS, path)
    assert _judged(keyless) == _judged(live)
    statuses = [s[0] for s in _judged(live)]
    assert INCONCLUSIVE in statuses and "FAIL" in statuses
    assert JUDGE_DISAGREE in _judged(live)[0][1]
    assert [r.agreement for r in keyless] == [r.agreement for r in live]


def _rewrite(path: Path, edit) -> None:
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    edit(lines)
    path.write_text("".join(json.dumps(l) + "\n" for l in lines))


def test_changed_checker_stamp_stops_with_both_hashes(tmp_path: Path) -> None:
    path, _ = _live(tmp_path)
    _rewrite(path, lambda ls: ls[0].update(checker_sha256="0" * 64))
    with pytest.raises(ReplayMismatchError, match="checker_sha256") as info:
        grade_keyless(ANSWERS, path)
    assert "0" * 64 in str(info.value) and grade_run.current_checker_sha256() in str(info.value)


@pytest.mark.parametrize("field", ["rubric_sha256", "answer_sha256"])
def test_changed_rubric_or_answer_hash_names_which(tmp_path: Path, field: str) -> None:
    path, _ = _live(tmp_path)
    _rewrite(path, lambda ls: ls[0].update({field: "f" * 64}))
    with pytest.raises(ReplayMismatchError, match=field):
        grade_keyless(ANSWERS, path)


def test_a_different_logged_verdict_names_the_criterion(tmp_path: Path) -> None:
    path, _ = _live(tmp_path)
    _rewrite(path, lambda ls: ls[0]["verdicts"][2].update(status="FAIL"))
    with pytest.raises(ReplayMismatchError, match="T1.C3"):
        grade_keyless(ANSWERS, path)


def test_unused_judge_lines_fail_the_replay(tmp_path: Path) -> None:
    path, _ = _live(tmp_path)
    with pytest.raises(ReplayMismatchError, match="unused"):
        grade_keyless(ANSWERS[:3], path)
