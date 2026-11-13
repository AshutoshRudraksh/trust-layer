"""Ticket 4 amendment: a configurable Judge B and a liveness preflight for the held out transfer run.

The pre-registered Judge B (muse-spark-open-1026, Baseten version wpgy40e) was retired by the provider on
Nov 13, 2026. Judge B becomes a named setting, recorded in run_meta.json, and a live run probes both judges
before any worker call. The probe is kept out of the run record. Every test here is offline.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from evals.test_pyx_transfer_run import KEYS, DeactivatedClient, FakeClient, _setup
from pyx.transfer_run import (JUDGE_B_PREREGISTERED, JudgeB, MetaChatJudge, RefuseToStart, parse_judge_b, preflight,
                              run_transfer)


def test_the_preregistered_judge_b_is_named_and_stays_the_default() -> None:
    assert JUDGE_B_PREREGISTERED == JudgeB("baseten", "meta-models/muse-spark-open-1026", "chat_completions")


@pytest.mark.parametrize("spec,expected", [
    ("baseten:meta-models/muse-spark-open", JudgeB("baseten", "meta-models/muse-spark-open", "chat_completions")),
    ("meta:muse-spark-1.3", JudgeB("meta", "muse-spark-1.3", "responses")),
])
def test_parse_judge_b(spec, expected) -> None:
    assert parse_judge_b(spec) == expected


@pytest.mark.parametrize("spec,why", [
    ("baseten:meta-llama/Llama-4-Maverick", "Llama"),
    ("meta:muse-spark-1.3-contributor", "distinct"),
    ("fireworks:accounts/x/models/muse-spark-open", "provider"),
    ("muse-spark-open", "provider"),
])
def test_parse_judge_b_refuses_llama_a_judge_a_twin_and_unknown_hosts(spec, why) -> None:
    with pytest.raises(RefuseToStart, match=why):
        parse_judge_b(spec)


def test_a_meta_hosted_judge_b_answers_chat_through_respond_with_its_own_model() -> None:
    inner = SimpleNamespace(api_key="k", calls=[])

    def respond(prompt, **params):
        inner.calls.append((prompt, params))
        return SimpleNamespace(output_text="PASS", dry_run=False)

    inner.respond = respond
    judge = MetaChatJudge(inner, "muse-spark-1.3")
    assert judge.chat("p", max_tokens=2048, temperature=0).output_text == "PASS"
    prompt, params = inner.calls[0]
    assert prompt == "p" and params["model"] == "muse-spark-1.3" and params["max_output_tokens"] == 2048
    assert params["temperature"] == 0 and params["role"] == "eval-runner"
    assert judge.api_key == "k"


def test_preflight_reports_both_judges_alive() -> None:
    ledger = SimpleNamespace(totals={"meta": 0.0, "baseten": 0.0})
    assert preflight(FakeClient(ledger, "meta"), FakeClient(ledger, "baseten")) == {"A": "PASS", "B": "PASS"}


def test_preflight_refuses_a_dead_judge_b_before_any_worker_call_or_file(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    live["b"] = DeactivatedClient(ledger, "baseten")
    out = tmp_path / "run"
    with pytest.raises(RefuseToStart, match="Judge B.*400.*deactivated"):
        run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha, probe=True)
    assert live["worker"].prompts == []
    assert not out.exists()


def test_preflight_refuses_a_judge_that_does_not_answer_pass_or_fail(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)

    class Chatty(FakeClient):
        def respond(self, prompt, **params):
            return SimpleNamespace(output_text="Sure! Happy to help.", input_tokens=1, output_tokens=1,
                                   cost_usd=0.0, dry_run=False, model="m")

    live["a"] = Chatty(ledger, "meta")
    with pytest.raises(RefuseToStart, match="Judge A"):
        run_transfer(tmp_path / "run", rubric, paper, live, ledger, env=KEYS, expected_sha256=sha, probe=True)
    assert live["worker"].prompts == []


def test_a_probed_run_records_judge_b_and_keeps_the_probe_out_of_the_record(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    judge_b = JudgeB("baseten", "meta-models/muse-spark-open", "chat_completions")
    out = tmp_path / "run"
    run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha, probe=True, judge_b=judge_b)
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["judge_b"] == {"provider": "baseten", "model": "meta-models/muse-spark-open",
                               "endpoint": "chat_completions"}
    assert meta["preflight"] == {"A": "PASS", "B": "PASS"}
    lines = [json.loads(l) for l in (out / "calls.jsonl").read_text().splitlines()]
    assert {l["model"] for l in lines if l["judge"] == "B"} == {"meta-models/muse-spark-open"}
    assert len([l for l in lines if l["judge"] == "A"]) == 20  # 10 answers x 2 judged criteria, no probe line
    spend = json.loads((out / "spend.json").read_text())
    assert spend["baseten"]["run_delta"] == pytest.approx(20 * 0.01)  # the probe's cost is outside the run


def test_a_meta_hosted_judge_b_is_metered_as_meta_spend(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    live["b"] = FakeClient(ledger, "meta")
    out = tmp_path / "run"
    run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha,
                 judge_b=JudgeB("meta", "muse-spark-1.3", "responses"))
    spend = json.loads((out / "spend.json").read_text())
    assert spend["meta"]["logged_cost_usd"] == pytest.approx(10 * 0.01 + 20 * 0.01 + 20 * 0.01)
    assert spend["baseten"]["logged_cost_usd"] == 0.0


def test_keyless_replay_uses_the_recorded_judge_b(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    judge_b = JudgeB("baseten", "meta-models/muse-spark-open", "chat_completions")
    first = tmp_path / "run"
    run_transfer(first, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha, probe=True, judge_b=judge_b)
    again = tmp_path / "replay"
    run_transfer(again, rubric, paper, None, None, env={}, src_log=first / "calls.jsonl", expected_sha256=sha)
    assert (again / "verdicts.tsv").read_bytes() == (first / "verdicts.tsv").read_bytes()
    assert json.loads((again / "run_meta.json").read_text())["judge_b"]["model"] == "meta-models/muse-spark-open"


def test_the_cli_takes_judge_b_defaults_to_the_preregistered_one_and_always_probes(tmp_path, monkeypatch) -> None:
    import pyx.transfer_run as tr
    ledger_file = tmp_path / "ledger.json"
    ledger_file.write_text('{"version": 1, "providers": {}}', encoding="utf-8")
    monkeypatch.setenv("PYX_SPEND_LEDGER", str(ledger_file))
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(tr, "verify_rubric", lambda path, expected_sha256=None: {})
    seen = {}
    monkeypatch.setattr(tr, "run_transfer", lambda *a, **k: seen.update(k) or {"answers": 10})
    base = ["--rubric", "r.json", "--paper", "p.txt", "--out", str(tmp_path / "run")]
    assert tr.main(base) == 0
    assert seen["probe"] is True and seen["judge_b"] == JUDGE_B_PREREGISTERED
    assert tr.main(base + ["--judge-b", "baseten:meta-models/muse-spark-open"]) == 0
    assert seen["probe"] is True
    assert seen["judge_b"] == JudgeB("baseten", "meta-models/muse-spark-open", "chat_completions")
