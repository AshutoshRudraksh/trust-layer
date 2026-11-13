"""Ticket 4: the held out transfer run script (docs/proposals/held-out-transfer-task.md).

Every test is offline. Fake clients stand in for Meta and Baseten; the one test that touches the real
MetaModelClient uses its keyless local fallback, which makes no network call, to prove the guard
refuses it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.meta_client import MetaModelClient
from agents.spend_ledger import SpendLedger
from pyx.transfer_run import (FallbackRefused, NoFallback, RefuseToStart, TransferAbort, committed_rubric_sha256,
                              earned_context, require_live_keys, run_transfer, verify_rubric)

ROOT = Path(__file__).resolve().parent.parent
# Muse ruling, Nov 13, 2026: the JSON freeze supersedes the Markdown freeze 2e7de886... for format only.
APPROVED_SHA = "3aec5d322432266a9010c7ce55b7c85c9498162a3b40b85684ca3f1bc5d48754"
KEYS = {"MODEL_API_KEY": "test-meta", "BASETEN_API_KEY": "test-baseten"}
PAPER = "SWE-agent stand in text for tests. Table 1 reports 12.47 percent resolved."


class FakeLedger:
    def __init__(self) -> None:
        self.totals = {"meta": 1.0, "baseten": 2.0}

    def total_usd(self, provider: str) -> float:
        return self.totals[provider]


class FakeClient:
    """Deterministic stand in for a live client. Judges always say PASS; the worker echoes a fixed answer."""

    def __init__(self, ledger: FakeLedger, provider: str, cost: float = 0.01, dry_run: bool = False,
                 api_key: str = "k") -> None:
        self.ledger, self.provider, self.cost, self.dry_run, self.api_key = ledger, provider, cost, dry_run, api_key
        self.prompts: list = []

    def _reply(self, prompt: str) -> SimpleNamespace:
        self.prompts.append(prompt)
        self.ledger.totals[self.provider] += self.cost
        text = "PASS" if "Reply with exactly one word" in prompt else "## Architecture\nx\n## Results\n12.47"
        return SimpleNamespace(output_text=text, input_tokens=10, output_tokens=5, cost_usd=self.cost,
                               dry_run=self.dry_run, model="m")

    def respond(self, prompt: str, **params) -> SimpleNamespace:
        return self._reply(prompt)

    def chat(self, prompt: str, **params) -> SimpleNamespace:
        return self._reply(prompt)


def _rubric(tmp_path: Path) -> tuple:
    rubric = json.loads((ROOT / "pyx" / "rubrics" / "T1.json").read_text(encoding="utf-8"))
    rubric["task_id"] = "H2"
    for i, c in enumerate(rubric["criteria"], start=1):
        c["id"] = f"H2.C{i}"
    rubric["criteria"][6].update({"type": "judged", "check": "judged", "expected": []})
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(rubric), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _setup(tmp_path: Path, cost: float = 0.01):
    rubric, sha = _rubric(tmp_path)
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER, encoding="utf-8")
    ledger = FakeLedger()
    live = {"worker": FakeClient(ledger, "meta", cost), "a": FakeClient(ledger, "meta", cost),
            "b": FakeClient(ledger, "baseten", cost)}
    return rubric, sha, paper, ledger, live


def test_the_committed_rubric_hash_is_the_approved_one() -> None:
    assert committed_rubric_sha256() == APPROVED_SHA


def test_a_rubric_whose_hash_differs_is_refused_before_anything_else(tmp_path) -> None:
    rubric, _, paper, ledger, live = _setup(tmp_path)
    out = tmp_path / "run"
    with pytest.raises(RefuseToStart, match="sha256"):
        run_transfer(out, rubric, paper, live, ledger, env={}, expected_sha256="0" * 64)
    assert not out.exists()
    assert all(c.prompts == [] for c in live.values())


def test_verify_rubric_defaults_to_the_committed_hash(tmp_path) -> None:
    rubric, _, _, _, _ = _setup(tmp_path)
    with pytest.raises(RefuseToStart, match=APPROVED_SHA[:12]):
        verify_rubric(rubric)


@pytest.mark.parametrize("env", [{}, {"MODEL_API_KEY": "x"}, {"BASETEN_API_KEY": "y"},
                                 {"MODEL_API_KEY": "", "BASETEN_API_KEY": "y"},
                                 {"MODEL_API_KEY": "x", "BASETEN_API_KEY": "  "}])
def test_a_live_run_refuses_to_start_without_both_keys(tmp_path, env) -> None:
    with pytest.raises(RefuseToStart, match="API_KEY"):
        require_live_keys(env)
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    with pytest.raises(RefuseToStart, match="API_KEY"):
        run_transfer(tmp_path / "run", rubric, paper, live, ledger, env=env, expected_sha256=sha)
    assert all(c.prompts == [] for c in live.values())


def test_the_real_meta_client_without_a_key_would_fall_back_and_the_guard_refuses_it(tmp_path) -> None:
    keyless = MetaModelClient(api_key="", ledger=SpendLedger(tmp_path / "ledger.json"))
    assert keyless.respond("ping", role="research", reasoning_effort="low", max_output_tokens=8).dry_run is True
    with pytest.raises(RefuseToStart, match="fallback"):
        NoFallback(keyless)


def test_any_fallback_response_is_refused_and_never_recorded(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    live["worker"] = FakeClient(ledger, "meta", dry_run=True)
    out = tmp_path / "run"
    with pytest.raises(FallbackRefused):
        run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    calls = out / "calls.jsonl"
    assert not calls.exists() or calls.read_text(encoding="utf-8") == ""
    assert not (out / "verdicts.tsv").exists()


def test_earned_context_is_the_one_approved_lesson() -> None:
    ctx = earned_context()
    assert ctx.lesson_ids == ("L_T1.C8_79e93c16",)
    assert ctx.arm == "earned_lessons"
    assert "define what auxiliary diagnostic columns" in ctx.text


def test_a_live_run_makes_5_paired_repetitions_and_records_spend_per_provider(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    out = tmp_path / "run"
    summary = run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    answers = [json.loads(l) for l in (out / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(a["rep"], a["arm"]) for a in answers] == [(r, arm) for r in range(5)
                                                        for arm in ("no_memory", "earned_lessons")]
    worker_prompts = live["worker"].prompts
    assert "L_T1.C8_79e93c16" not in worker_prompts[0] and "L_T1.C8_79e93c16" in worker_prompts[1]
    assert all(PAPER in p for p in worker_prompts)
    assert not any(c["verdict"] in p for p in worker_prompts for c in json.loads(rubric.read_text())["criteria"])
    spend = json.loads((out / "spend.json").read_text())
    assert set(spend) == {"meta", "baseten"}
    assert spend["meta"]["run_delta"] == pytest.approx(10 * 0.01 + 10 * 2 * 0.01)
    assert spend["baseten"]["run_delta"] == pytest.approx(10 * 2 * 0.01)
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["rubric_sha256"] == sha and meta["paper_sha256"] == hashlib.sha256(PAPER.encode()).hexdigest()
    assert (out / "rubric.json").read_bytes() == rubric.read_bytes()
    assert summary["answers"] == 10


def test_keyless_replay_reproduces_the_verdicts_byte_for_byte(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    first = tmp_path / "run"
    run_transfer(first, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    again = tmp_path / "replay"
    run_transfer(again, rubric, paper, None, None, env={}, src_log=first / "calls.jsonl", expected_sha256=sha)
    assert (again / "verdicts.tsv").read_bytes() == (first / "verdicts.tsv").read_bytes()
    assert (again / "answers.jsonl").read_bytes() == (first / "answers.jsonl").read_bytes()


def test_keyless_replay_refuses_a_different_paper(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    first = tmp_path / "run"
    run_transfer(first, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    paper.write_text(PAPER + " edited", encoding="utf-8")
    with pytest.raises(RefuseToStart, match="paper"):
        run_transfer(tmp_path / "replay", rubric, paper, None, None, env={}, src_log=first / "calls.jsonl",
                     expected_sha256=sha)


@pytest.mark.parametrize("provider,cost", [("meta", 0.2), ("baseten", 0.4)])
def test_spend_caps_abort_the_run_in_code(tmp_path, provider, cost) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path)
    for client in live.values():
        if client.provider == provider:
            client.cost = cost
    out = tmp_path / "run"
    with pytest.raises(TransferAbort, match=provider):
        run_transfer(out, rubric, paper, live, ledger, env=KEYS, expected_sha256=sha)
    assert (out / "abort.txt").read_text().startswith(f"ABORT: new {provider} spend")
    assert len((out / "answers.jsonl").read_text().splitlines()) < 10
    assert json.loads((out / "spend.json").read_text())[provider]["run_delta"] > 0
    assert not (out / "rubric.json").exists()


def test_the_hard_stop_aborts_on_combined_new_spend(tmp_path) -> None:
    rubric, sha, paper, ledger, live = _setup(tmp_path, cost=1.0)
    with pytest.raises(TransferAbort, match="hard stop"):
        run_transfer(tmp_path / "run", rubric, paper, live, ledger, env=KEYS, expected_sha256=sha,
                     caps={"meta": 100.0, "baseten": 100.0}, hard_stop_usd=5.0)


def test_default_caps_are_the_approved_ones() -> None:
    from pyx.transfer_run import CAPS, HARD_STOP_USD, REPS
    assert (CAPS, HARD_STOP_USD, REPS) == ({"meta": 3.0, "baseten": 5.0}, 25.0, 5)
