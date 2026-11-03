"""PR H9d tests: the phase engine calls each live client through its real method.

Written against the crash of run pyx_h9_20261102: phase 1 stopped on its first Judge B call
with AttributeError, BasetenClient has no attribute respond, because LogFirst aliased chat
to respond while the phase test fake offered both methods. Fakes only; no network.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agents.baseten_client import BasetenClient
from agents.meta_client import MetaModelClient
from agents.spend_ledger import SpendLedger
from pyx.phase import Engine, phase1
from pyx.run import main
from evals.test_pyx_phase1 import BasetenFake, Ledger, MetaFake, _eval, _live
from evals.test_pyx_phase2 import _PoisonFake


class ChatOnlyBaseten:
    """Stands for BasetenClient with exactly its public surface; records how chat was called."""

    def __init__(self):
        self.seen = []

    def chat(self, prompt, **kw):
        self.seen.append((prompt, kw.get("max_tokens"), kw.get("temperature")))
        return NS(output_text="FAIL", input_tokens=1, output_tokens=1, cost_usd=0.0, model="m")

    def estimate_cost_usd(self, *a, **kw):
        raise AssertionError("phase code must not call estimate_cost_usd on a client")


def _surface(cls):
    return {n for n in dir(cls) if not n.startswith("_") and callable(getattr(cls, n))}


def test_engine_calls_judge_b_through_chat_with_max_tokens_and_temperature(tmp_path) -> None:
    b = ChatOnlyBaseten()
    out = tmp_path / "out"
    out.mkdir()
    eng = Engine(out, "R", {"b": b}, None)
    eng.c["b"].chat("judge prompt", max_tokens=2048, temperature=0)
    assert b.seen == [("judge prompt", 2048, 0)]


def test_phase1_runs_cycle0_with_a_chat_only_judge_b(tmp_path) -> None:
    meta, live = _live()
    b = ChatOnlyBaseten()
    live = {**live, "b": b}
    ev, h = _eval(tmp_path)
    out = tmp_path / "out"
    assert phase1(out, "R", h, 3, live=live, ledger=Ledger(), eval_path=ev) == 0
    assert b.seen and all(mt == 2048 and t == 0 for _, mt, t in b.seen)
    assert (out / "spend.json").exists()


@pytest.mark.parametrize("fake,real", [(MetaFake, MetaModelClient), (BasetenFake, BasetenClient),
                                       (_PoisonFake, MetaModelClient), (ChatOnlyBaseten, BasetenClient),
                                       (Ledger, SpendLedger)])
def test_fake_surface_matches_the_real_client_it_stands_for(fake, real) -> None:
    assert _surface(fake) == _surface(real)


class _Boom:
    def __init__(self, *a, **kw):
        raise AssertionError("no client or ledger may be constructed before the shared ledger guard")


def test_live_phase_refuses_without_a_shared_ledger_env(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("PYX_SPEND_LEDGER", raising=False)
    monkeypatch.setattr("agents.spend_ledger.SpendLedger", _Boom)
    monkeypatch.setattr("agents.meta_client.MetaModelClient", _Boom)
    monkeypatch.setattr("agents.baseten_client.BasetenClient", _Boom)
    monkeypatch.setattr("pyx.worker.worker_client", _Boom)
    ev, h = _eval(tmp_path)
    out = tmp_path / "o"
    rc = main(["phase1", "--run-id", "X", "--out", str(out), "--eval", str(ev),
               "--eval-sha256", h, "--reps", "3"])
    assert rc == 2
    assert not out.exists()


def test_live_phase_with_the_env_set_to_an_existing_file_passes_the_guard(monkeypatch, tmp_path) -> None:
    ledger_file = tmp_path / "shared.json"
    ledger_file.write_text("{}\n")
    monkeypatch.setenv("PYX_SPEND_LEDGER", str(ledger_file))
    meta, live = _live()
    monkeypatch.setattr("agents.spend_ledger.SpendLedger", lambda *a, **kw: Ledger())
    monkeypatch.setattr("agents.meta_client.MetaModelClient", lambda *a, **kw: meta)
    monkeypatch.setattr("agents.baseten_client.BasetenClient", lambda *a, **kw: live["b"])
    monkeypatch.setattr("pyx.worker.worker_client", lambda *a, **kw: meta)
    ev, h = _eval(tmp_path)
    out = tmp_path / "o"
    rc = main(["phase1", "--run-id", "X", "--out", str(out), "--eval", str(ev),
               "--eval-sha256", h, "--reps", "3"])
    assert rc == 0
    assert (out / "status.txt").read_text().strip() == "awaiting pairs"


class _ScriptLedger:
    def __init__(self):
        self.totals = {"meta": 1.5, "baseten": 2.5}

    def total_usd(self, provider):
        return self.totals[provider]


def test_spend_report_shows_start_delta_and_cumulative(tmp_path) -> None:
    led = _ScriptLedger()
    out = tmp_path / "out"
    out.mkdir()
    eng = Engine(out, "R", None, led)
    led.totals = {"meta": 1.9, "baseten": 2.9}
    eng.spend_report()
    data = json.loads((out / "spend.json").read_text())
    assert data["meta"]["start"] == 1.5 and data["meta"]["now"] == 1.9
    assert data["meta"]["run_delta"] == pytest.approx(0.4) and data["meta"]["cumulative"] == 1.9
    assert data["baseten"]["start"] == 2.5 and data["baseten"]["run_delta"] == pytest.approx(0.4)
