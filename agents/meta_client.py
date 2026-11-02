from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import httpx

from .http_retry import post_with_backoff
from .spend_ledger import SpendLedger
from .tracing import TraceCollector

LEDGER_PROVIDER = "meta"


def _first_count(usage: Dict[str, Any], keys: tuple, fallback: int) -> int:
    """First token count present in usage; a reported 0 is kept, not replaced."""
    for key in keys:
        if usage.get(key) is not None:
            return int(usage[key])
    return fallback


class BudgetCapExceededError(RuntimeError):
    """Raised when an API call would exceed the $150.00 hackathon credit cap or when free credits are not yet applied."""


class InvalidReasoningEffortError(ValueError):
    """Raised when reasoning effort is set to an unsupported value such as 'none'."""


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    input_per_million_usd: float
    output_per_million_usd: float
    context_window_tokens: int


MODEL_PRICING_TABLE: Dict[str, ModelPricing] = {
    "muse-spark-1.3": ModelPricing(
        model_id="muse-spark-1.3",
        input_per_million_usd=1.25,
        output_per_million_usd=4.25,
        context_window_tokens=1_000_000,
    ),
    "muse-spark-1.3-contributor": ModelPricing(
        model_id="muse-spark-1.3-contributor",
        input_per_million_usd=0.10,
        output_per_million_usd=0.20,
        context_window_tokens=1_000_000,
    ),
}

ROLE_TO_DEFAULT_MODEL: Dict[str, str] = {
    "chief-of-staff": "muse-spark-1.3-contributor",
    "pipeline": "muse-spark-1.3-contributor",
    "research": "muse-spark-1.3-contributor",
    "code-review": "muse-spark-1.3-contributor",
    "memory-consolidation": "muse-spark-1.3-contributor",
    "eval-runner": "muse-spark-1.3-contributor",
}

DEFAULT_MODEL = "muse-spark-1.3-contributor"

VALID_REASONING_EFFORTS = frozenset({"low", "medium", "high", "max"})


@dataclass(frozen=True)
class ModelResponse:
    response_id: str
    model: str
    role: str
    output_text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_spend_usd: float
    dry_run: bool
    endpoint: str


class MetaModelClient:
    """
    OpenAI-compatible client for the Meta Model API (https://api.meta.ai/v1/responses
    and https://api.meta.ai/v1/chat/completions) with:
    1. Role-aware model routing across muse-spark-1.3 and muse-spark-1.3-contributor.
    2. Strict validation that reasoning.effort is one of low, medium, high, or max (never none).
    3. Hard $150.00 credit cap ledger and unapplied-credit card protection guard.
    4. Deterministic local fallback when MODEL_API_KEY is not set in the environment.
    """

    DEFAULT_BASE_URL = "https://api.meta.ai/v1"
    DEFAULT_BUDGET_CAP_USD = 40.00  # hard stop agreed for the hackathon; credit is $150
    DEFAULT_TIMEOUT_S = 40.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        budget_cap_usd: float = DEFAULT_BUDGET_CAP_USD,
        free_credits_applied: bool = True,
        require_free_credits_applied: bool = True,
        tracer: Optional[TraceCollector] = None,
        ledger: Optional[SpendLedger] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("MODEL_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.budget_cap_usd = float(budget_cap_usd)
        self.free_credits_applied = free_credits_applied
        self.require_free_credits_applied = require_free_credits_applied
        self.cumulative_spend_usd: float = 0.0
        self.tracer = tracer or TraceCollector()
        # Live spend persists across processes in the ledger file; the $40 hard
        # stop is checked against that cumulative total before every call.
        # Dry run spend is simulated and stays in this process only.
        self.ledger = ledger or SpendLedger()
        self.dry_run_spend_usd: float = 0.0
        self.timeout_s = timeout_s
        self._transport = transport
        self._sleep = sleep

    def estimate_cost_usd(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        pricing = MODEL_PRICING_TABLE.get(model, MODEL_PRICING_TABLE["muse-spark-1.3"])
        input_cost = (max(0, input_tokens) / 1_000_000.0) * pricing.input_per_million_usd
        output_cost = (max(0, output_tokens) / 1_000_000.0) * pricing.output_per_million_usd
        return round(input_cost + output_cost, 8)

    def _validate_reasoning_effort(self, reasoning_effort: str) -> str:
        normalized = reasoning_effort.strip().lower()
        if normalized not in VALID_REASONING_EFFORTS:
            raise InvalidReasoningEffortError(
                f"Invalid reasoning effort '{reasoning_effort}'. Meta Model API requires one of {sorted(VALID_REASONING_EFFORTS)} and never 'none'."
            )
        return normalized

    def _check_budget_guard(self, projected_cost_usd: float) -> None:
        if self.require_free_credits_applied and not self.free_credits_applied:
            raise BudgetCapExceededError(
                "Meta Model API call blocked: free hackathon credits ($150.00) are not yet marked as applied on the Billing tab. "
                "Blocking execution to prevent unintended personal card charges."
            )
        spent = self.ledger.total_usd(LEDGER_PROVIDER) + self.dry_run_spend_usd
        if spent + projected_cost_usd > self.budget_cap_usd:
            raise BudgetCapExceededError(
                f"Meta Model API call blocked: projected total spend "
                f"${spent + projected_cost_usd:.4f} exceeds the ${self.budget_cap_usd:.2f} budget cap."
            )

    def build_responses_payload(
        self,
        prompt: str,
        role: str = "chief-of-staff",
        model: Optional[str] = None,
        reasoning_effort: str = "high",
        max_output_tokens: int = 1024,
        previous_response_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        effort = self._validate_reasoning_effort(reasoning_effort)
        selected_model = model or ROLE_TO_DEFAULT_MODEL.get(role, DEFAULT_MODEL)
        payload: Dict[str, Any] = {
            "model": selected_model,
            "input": prompt,
            "reasoning": {"effort": effort},
            "max_output_tokens": max_output_tokens,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        return payload

    def respond(
        self,
        prompt: str,
        role: str = "chief-of-staff",
        model: Optional[str] = None,
        reasoning_effort: str = "high",
        max_output_tokens: int = 1024,
        previous_response_id: Optional[str] = None,
        endpoint_style: str = "responses",
    ) -> ModelResponse:
        selected_model = model or ROLE_TO_DEFAULT_MODEL.get(role, DEFAULT_MODEL)
        payload = self.build_responses_payload(
            prompt=prompt,
            role=role,
            model=selected_model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            previous_response_id=previous_response_id,
        )

        estimated_input_tokens = max(1, len(prompt) // 4)
        projected_cost = self.estimate_cost_usd(
            model=selected_model,
            input_tokens=estimated_input_tokens,
            output_tokens=max_output_tokens,
        )
        self._check_budget_guard(projected_cost)

        endpoint_path = "/responses" if endpoint_style == "responses" else "/chat/completions"
        full_endpoint = f"{self.base_url}{endpoint_path}"

        with self.tracer.start_span(
            name=f"meta_model_api.{endpoint_style}",
            attributes={"role": role, "model": selected_model, "reasoning_effort": reasoning_effort},
        ) as span:
            if not self.api_key:
                simulated_output = (
                    f"[{role}:{selected_model}] Verified local dry-run response for prompt ({len(prompt)} chars)."
                )
                actual_output_tokens = max(1, len(simulated_output) // 4)
                actual_cost = self.estimate_cost_usd(
                    model=selected_model,
                    input_tokens=estimated_input_tokens,
                    output_tokens=actual_output_tokens,
                )
                self.cumulative_spend_usd = round(self.cumulative_spend_usd + actual_cost, 8)
                self.dry_run_spend_usd = round(self.dry_run_spend_usd + actual_cost, 8)
                span.attributes["dry_run"] = True
                span.attributes["cost_usd"] = actual_cost
                return ModelResponse(
                    response_id="resp_dryrun_001",
                    model=selected_model,
                    role=role,
                    output_text=simulated_output,
                    input_tokens=estimated_input_tokens,
                    output_tokens=actual_output_tokens,
                    cost_usd=actual_cost,
                    cumulative_spend_usd=self.cumulative_spend_usd,
                    dry_run=True,
                    endpoint=full_endpoint,
                )

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            if endpoint_style == "chat_completions":
                request_body: Dict[str, Any] = {
                    "model": selected_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_output_tokens,
                }
            else:
                request_body = payload

            with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
                resp = post_with_backoff(
                    client, full_endpoint, headers=headers, json=request_body, sleep=self._sleep
                )
                data = resp.json()

            usage = data.get("usage", {})
            in_tok = _first_count(usage, ("input_tokens", "prompt_tokens"), estimated_input_tokens)
            out_tok = _first_count(usage, ("output_tokens", "completion_tokens"), 64)
            actual_cost = self.estimate_cost_usd(selected_model, in_tok, out_tok)
            # The money is spent once the reply arrives, so record it before
            # anything else; the guard before the next call enforces the cap.
            response_id = str(data.get("id") or "")
            call_id = f"{response_id}:{uuid.uuid4().hex}" if response_id else uuid.uuid4().hex
            self.ledger.record(LEDGER_PROVIDER, call_id, actual_cost)
            self.cumulative_spend_usd = round(self.cumulative_spend_usd + actual_cost, 8)

            output_text = data.get("output_text", "")
            if not output_text and "choices" in data and data["choices"]:
                output_text = data["choices"][0].get("message", {}).get("content", "")

            span.attributes["dry_run"] = False
            span.attributes["cost_usd"] = actual_cost

            return ModelResponse(
                response_id=str(data.get("id", "resp_live")),
                model=selected_model,
                role=role,
                output_text=output_text,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=actual_cost,
                cumulative_spend_usd=self.cumulative_spend_usd,
                dry_run=False,
                endpoint=full_endpoint,
            )
