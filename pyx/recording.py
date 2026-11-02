"""RecordingClient: wraps a judge client and logs every call attempt.

It exposes the same respond and chat methods as MetaModelClient and
BasetenClient, so judges.py needs no change. Each attempt becomes one call log
line with its prompt, raw reply, tokens, cost and latency. Judge faults
(EmptyReplyError, RateLimitedError) are logged with outcome "error" and
re raised, so a keyless replay can reproduce them. A budget stop is not a call:
it is re raised without a log line. Any other attribute, such as the ledger,
passes through to the wrapped client.
"""
from __future__ import annotations

import time
from typing import Any

from agents.http_retry import RateLimitedError
from agents.meta_client import EmptyReplyError
from pyx.call_log import CallLog

_LOGGED_FAULTS = (EmptyReplyError, RateLimitedError)


class RecordingClient:
    def __init__(self, inner: Any, log: CallLog, *, judge: str, model: str, endpoint: str,
                 held_out: bool = False, kind: str = "judge") -> None:
        self._inner, self._log, self._kind = inner, log, kind
        self._judge, self._model, self._endpoint, self._held_out = judge, model, endpoint, held_out

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _reasoning_tokens(self) -> int:
        tracer = getattr(self._inner, "tracer", None)
        spans = tracer.list_spans() if tracer is not None else []
        return int(spans[-1].attributes.get("reasoning_tokens") or 0) if spans else 0

    def _call(self, method: str, prompt: str, **kwargs: Any) -> Any:
        common = dict(judge=self._judge, model=self._model, endpoint=self._endpoint, params=kwargs,
                      prompt=prompt, held_out=self._held_out, kind=self._kind)
        start = time.monotonic()
        try:
            resp = getattr(self._inner, method)(prompt, **kwargs)
        except _LOGGED_FAULTS as exc:
            self._log.append_judge(**common, reply="", outcome="error", error=f"{type(exc).__name__}: {exc}",
                                   input_tokens=0, output_tokens=0, reasoning_tokens=self._reasoning_tokens(),
                                   cost_usd=0.0, latency_s=round(time.monotonic() - start, 3))
            raise
        self._log.append_judge(**common, reply=resp.output_text, outcome="ok", input_tokens=resp.input_tokens,
                               output_tokens=resp.output_tokens, reasoning_tokens=self._reasoning_tokens(),
                               cost_usd=resp.cost_usd, latency_s=round(time.monotonic() - start, 3))
        return resp

    def respond(self, prompt: str, **kwargs: Any) -> Any:
        return self._call("respond", prompt, **kwargs)

    def chat(self, prompt: str, **kwargs: Any) -> Any:
        return self._call("chat", prompt, **kwargs)
