"""Baseten client for Pyx Judge B (Muse Spark Open, a Meta model).

Same boundary rules as MetaModelClient: 40 s timeout, 429 backoff, a trace span
per call, and cost recorded in the persistent spend ledger under "baseten".
Baseten has no hard stop. Its cumulative spend is compared with a $25 guide
and a warning is raised when the guide is passed; the call still goes out.
The key is read from BASETEN_API_KEY only.
"""
from __future__ import annotations

import os
import time
import uuid
import warnings
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

from .http_retry import post_with_backoff
from .meta_client import ModelPricing
from .spend_ledger import SpendLedger
from .tracing import TraceCollector

BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"
BASETEN_MODEL = "meta-models/muse-spark-open-1026"
BASETEN_GUIDE_USD = 25.0
LEDGER_PROVIDER = "baseten"

# ASSUMPTION: Baseten's Muse Spark Open library page lists $1.25 input and
# $4.25 output per 1M tokens for the slug meta-models/muse-spark-open. No page
# names the 1026 slug, so this price is applied to it as an assumption, approved
# by Ashutosh for PR C1. Correct it if the Baseten dashboard shows another rate.
BASETEN_PRICING = ModelPricing(
    model_id=BASETEN_MODEL,
    input_per_million_usd=1.25,
    output_per_million_usd=4.25,
    context_window_tokens=0,  # not used for cost; not published on that page
)


@dataclass(frozen=True)
class BasetenResponse:
    response_id: str
    model: str
    output_text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_spend_usd: float
    pricing_assumed: bool


class BasetenClient:
    DEFAULT_TIMEOUT_S = 40.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = BASETEN_MODEL,
        ledger: Optional[SpendLedger] = None,
        tracer: Optional[TraceCollector] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        guide_usd: float = BASETEN_GUIDE_USD,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("BASETEN_API_KEY", "")
        self.model = model
        self.ledger = ledger or SpendLedger()
        self.tracer = tracer or TraceCollector()
        self.timeout_s = timeout_s
        self.guide_usd = guide_usd
        self._transport = transport
        self._sleep = sleep

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        p = BASETEN_PRICING
        cost = (max(0, input_tokens) / 1e6) * p.input_per_million_usd + (
            max(0, output_tokens) / 1e6
        ) * p.output_per_million_usd
        return round(cost, 8)

    def chat(self, prompt: str, max_tokens: int = 512, temperature: float = 0.0) -> BasetenResponse:
        if not self.api_key:
            raise RuntimeError("BASETEN_API_KEY is not set; Judge B cannot run.")
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with self.tracer.start_span(
            name="baseten.chat_completions",
            attributes={"model": self.model, "max_tokens": max_tokens, "temperature": temperature},
        ) as span:
            with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
                resp = post_with_backoff(client, BASETEN_URL, headers=headers, json=body, sleep=self._sleep)
            data = resp.json()
            usage = data.get("usage") or {}
            in_tok = int(usage.get("prompt_tokens") or 0)
            out_tok = int(usage.get("completion_tokens") or 0)
            cost = self.estimate_cost_usd(in_tok, out_tok)
            call_id = str(data.get("id") or "")
            call_id = f"{call_id}:{uuid.uuid4().hex}" if call_id else uuid.uuid4().hex
            total = self.ledger.record(LEDGER_PROVIDER, call_id, cost)
            choices = data.get("choices") or [{}]
            text = (choices[0].get("message") or {}).get("content") or ""
            span.attributes.update(
                {"cost_usd": cost, "input_tokens": in_tok, "output_tokens": out_tok,
                 "cumulative_spend_usd": total, "pricing_assumed": True}
            )
        if total > self.guide_usd:
            warnings.warn(
                f"Baseten cumulative spend ${total:.4f} is past the ${self.guide_usd:.2f} guide.",
                UserWarning,
            )
        return BasetenResponse(
            response_id=call_id, model=self.model, output_text=text, input_tokens=in_tok,
            output_tokens=out_tok, cost_usd=cost, cumulative_spend_usd=total, pricing_assumed=True,
        )
