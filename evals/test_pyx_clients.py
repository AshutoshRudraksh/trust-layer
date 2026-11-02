"""PR C1 tests: persistent spend ledger, 429 backoff, Meta and Baseten clients.

The network is mocked with httpx.MockTransport. No live calls are made.
Fake keys below are test strings, not real credentials.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, List

import httpx
import pytest

from agents.baseten_client import (
    BASETEN_GUIDE_USD,
    BASETEN_PRICING,
    BasetenClient,
)
from agents.http_retry import RateLimitedError, post_with_backoff
from agents.meta_client import BudgetCapExceededError, MetaModelClient
from agents.spend_ledger import SpendLedger

FAKE_META_KEY = "test-meta-key-not-real-0001"
FAKE_BASETEN_KEY = "test-baseten-key-not-real-0002"


def _transport(handler: Callable[[httpx.Request], httpx.Response], seen: List[httpx.Request]):
    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped)


def _chat_ok(text: str = "PASS", prompt_tokens: int = 100, completion_tokens: int = 20) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl_test",
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        },
    )


def _meta_ok(text: str = "PASS", in_tok: int = 100, out_tok: int = 20, rid: str = "resp_test") -> httpx.Response:
    return httpx.Response(
        200,
        json={"id": rid, "output_text": text, "usage": {"input_tokens": in_tok, "output_tokens": out_tok}},
    )


# Spend ledger


def test_ledger_starts_empty_and_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "runs" / "spend_ledger.json"
    first = SpendLedger(path)
    assert first.total_usd("meta") == 0.0
    first.record("meta", "call_1", 0.25)
    first.record("baseten", "call_2", 0.5)
    second = SpendLedger(path)
    assert second.total_usd("meta") == pytest.approx(0.25)
    assert second.total_usd("baseten") == pytest.approx(0.5)


def test_ledger_record_is_idempotent_per_call_id(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "ledger.json")
    ledger.record("meta", "call_1", 0.25)
    ledger.record("meta", "call_1", 0.25)
    assert ledger.total_usd("meta") == pytest.approx(0.25)


def test_ledger_write_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = SpendLedger(path)
    ledger.record("meta", "call_1", 0.1)
    assert json.loads(path.read_text())["providers"]["meta"]["total_usd"] == pytest.approx(0.1)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "ledger.json" and not p.name.endswith(".lock")]
    assert leftovers == []


def test_ledger_crash_during_write_keeps_previous_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ledger.json"
    ledger = SpendLedger(path)
    ledger.record("meta", "call_1", 0.1)

    def boom(src, dst):  # simulates a crash between temp write and rename
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        ledger.record("meta", "call_2", 0.2)
    monkeypatch.undo()
    assert SpendLedger(path).total_usd("meta") == pytest.approx(0.1)


def test_ledger_snapshot_is_readable_for_run_reports(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "ledger.json")
    ledger.record("meta", "a", 1.0)
    ledger.record("baseten", "b", 2.0)
    snap = ledger.snapshot()
    assert snap["meta"]["total_usd"] == pytest.approx(1.0)
    assert snap["meta"]["calls"] == 1
    assert snap["baseten"]["total_usd"] == pytest.approx(2.0)


# Backoff


def test_backoff_retries_429_at_1_2_4_seconds_then_raises() -> None:
    seen: List[httpx.Request] = []
    sleeps: List[float] = []
    transport = _transport(lambda r: httpx.Response(429), seen)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(RateLimitedError):
            post_with_backoff(client, "https://example.test/x", headers={}, json={}, sleep=sleeps.append)
    assert len(seen) == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_backoff_honors_retry_after_then_succeeds() -> None:
    seen: List[httpx.Request] = []
    sleeps: List[float] = []
    responses = [httpx.Response(429, headers={"Retry-After": "7"}), _chat_ok()]
    transport = _transport(lambda r: responses.pop(0), seen)
    with httpx.Client(transport=transport) as client:
        resp = post_with_backoff(client, "https://example.test/x", headers={}, json={}, sleep=sleeps.append)
    assert resp.status_code == 200
    assert sleeps == [7.0]


# Meta client


def test_meta_client_uses_40s_timeout_and_low_effort_for_judges(tmp_path: Path) -> None:
    assert MetaModelClient.DEFAULT_TIMEOUT_S == 40.0
    seen: List[httpx.Request] = []
    client = MetaModelClient(
        api_key=FAKE_META_KEY,
        ledger=SpendLedger(tmp_path / "l.json"),
        transport=_transport(lambda r: _meta_ok(), seen),
        sleep=lambda s: None,
    )
    client.respond(prompt="grade this", role="eval-runner", reasoning_effort="low", max_output_tokens=512)
    body = json.loads(seen[0].content)
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 512
    assert seen[0].extensions["timeout"]["read"] == 40.0


def test_meta_client_retries_429_then_records_spend_in_persistent_ledger(tmp_path: Path) -> None:
    seen: List[httpx.Request] = []
    sleeps: List[float] = []
    responses = [httpx.Response(429), _meta_ok(in_tok=1_000_000, out_tok=0)]
    ledger_path = tmp_path / "l.json"
    client = MetaModelClient(
        api_key=FAKE_META_KEY,
        ledger=SpendLedger(ledger_path),
        transport=_transport(lambda r: responses.pop(0), seen),
        sleep=sleeps.append,
    )
    resp = client.respond(prompt="x", role="eval-runner", reasoning_effort="low", max_output_tokens=512)
    assert sleeps == [1.0]
    assert resp.cost_usd == pytest.approx(0.10)
    assert SpendLedger(ledger_path).total_usd("meta") == pytest.approx(0.10)


def test_meta_hard_stop_uses_cumulative_total_across_processes(tmp_path: Path) -> None:
    ledger_path = tmp_path / "l.json"
    SpendLedger(ledger_path).record("meta", "earlier_process_call", 39.9999)
    seen: List[httpx.Request] = []
    client = MetaModelClient(
        api_key=FAKE_META_KEY,
        ledger=SpendLedger(ledger_path),
        transport=_transport(lambda r: _meta_ok(), seen),
        sleep=lambda s: None,
    )
    with pytest.raises(BudgetCapExceededError):
        client.respond(prompt="x" * 4000, role="eval-runner", reasoning_effort="low", max_output_tokens=512)
    assert seen == []


def test_meta_key_never_appears_in_spans_or_errors(tmp_path: Path) -> None:
    seen: List[httpx.Request] = []
    client = MetaModelClient(
        api_key=FAKE_META_KEY,
        ledger=SpendLedger(tmp_path / "l.json"),
        transport=_transport(lambda r: httpx.Response(429), seen),
        sleep=lambda s: None,
    )
    with pytest.raises(RateLimitedError) as info:
        client.respond(prompt="x", role="eval-runner", reasoning_effort="low")
    assert FAKE_META_KEY not in str(info.value)
    for span in client.tracer.list_spans():
        assert FAKE_META_KEY not in json.dumps(span.attributes, default=str)


# Baseten client


def test_baseten_pricing_is_the_labeled_assumption() -> None:
    assert BASETEN_PRICING.model_id == "meta-models/muse-spark-open-1026"
    assert BASETEN_PRICING.input_per_million_usd == 1.25
    assert BASETEN_PRICING.output_per_million_usd == 4.25
    assert BASETEN_GUIDE_USD == 25.0


def test_baseten_request_shape_timeout_and_auth(tmp_path: Path) -> None:
    seen: List[httpx.Request] = []
    client = BasetenClient(
        api_key=FAKE_BASETEN_KEY,
        ledger=SpendLedger(tmp_path / "l.json"),
        transport=_transport(lambda r: _chat_ok(), seen),
        sleep=lambda s: None,
    )
    resp = client.chat("grade this")
    req = seen[0]
    assert str(req.url) == "https://inference.baseten.co/v1/chat/completions"
    assert req.headers["Authorization"] == f"Bearer {FAKE_BASETEN_KEY}"
    body = json.loads(req.content)
    assert body["model"] == "meta-models/muse-spark-open-1026"
    assert body["temperature"] == 0
    assert body["max_tokens"] == 512
    assert body["messages"] == [{"role": "user", "content": "grade this"}]
    assert req.extensions["timeout"]["read"] == 40.0
    assert resp.output_text == "PASS"


def test_baseten_cost_lands_in_persistent_ledger_and_span(tmp_path: Path) -> None:
    seen: List[httpx.Request] = []
    ledger_path = tmp_path / "l.json"
    client = BasetenClient(
        api_key=FAKE_BASETEN_KEY,
        ledger=SpendLedger(ledger_path),
        transport=_transport(lambda r: _chat_ok(prompt_tokens=1_000_000, completion_tokens=1_000_000), seen),
        sleep=lambda s: None,
    )
    resp = client.chat("x")
    assert resp.cost_usd == pytest.approx(5.50)
    assert SpendLedger(ledger_path).total_usd("baseten") == pytest.approx(5.50)
    span = client.tracer.list_spans()[-1]
    assert span.attributes["model"] == "meta-models/muse-spark-open-1026"
    assert span.attributes["cost_usd"] == pytest.approx(5.50)
    assert FAKE_BASETEN_KEY not in json.dumps(span.attributes, default=str)


def test_baseten_over_guide_warns_but_does_not_block(tmp_path: Path) -> None:
    ledger_path = tmp_path / "l.json"
    SpendLedger(ledger_path).record("baseten", "earlier", 30.0)
    seen: List[httpx.Request] = []
    client = BasetenClient(
        api_key=FAKE_BASETEN_KEY,
        ledger=SpendLedger(ledger_path),
        transport=_transport(lambda r: _chat_ok(), seen),
        sleep=lambda s: None,
    )
    with pytest.warns(UserWarning, match="guide"):
        client.chat("x")
    assert len(seen) == 1


def test_baseten_429_backoff_and_missing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[httpx.Request] = []
    sleeps: List[float] = []
    client = BasetenClient(
        api_key=FAKE_BASETEN_KEY,
        ledger=SpendLedger(tmp_path / "l.json"),
        transport=_transport(lambda r: httpx.Response(429), seen),
        sleep=sleeps.append,
    )
    with pytest.raises(RateLimitedError) as info:
        client.chat("x")
    assert sleeps == [1.0, 2.0, 4.0]
    assert FAKE_BASETEN_KEY not in str(info.value)

    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BASETEN_API_KEY"):
        BasetenClient(ledger=SpendLedger(tmp_path / "l2.json")).chat("x")
