"""ReplayClient: serves judge replies from a call log, with no key and no network.

It has the same respond and chat methods as the real judge clients, so
grade_answer runs unchanged. Each call computes the replay key from the judge,
model and endpoint recorded in the log, the prompt and the call params, and
serves the next unused line with that key in recorded order. An error line
re raises the same error. A call with no unused line raises ReplayMissError:
there is no fallback to a dry run, a live call or a default verdict. This module
never imports the real client classes and never reads the environment.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List

from agents.http_retry import RateLimitedError
from agents.meta_client import EmptyReplyError
from pyx.call_log import replay_key

_ERRORS = {"EmptyReplyError": EmptyReplyError, "RateLimitedError": RateLimitedError}


class ReplayMissError(RuntimeError):
    """The call log has no unused entry for this call."""


@dataclass(frozen=True)
class ReplayResponse:
    output_text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


class ReplayClient:
    def __init__(self, lines: List[Dict[str, Any]], judge: str) -> None:
        self.judge = judge
        self._lines = [l for l in lines if l.get("kind") == "judge" and l.get("judge") == judge]
        self.model = self._lines[0]["model"] if self._lines else ""
        self.endpoint = self._lines[0]["endpoint"] if self._lines else ""
        self._served: set = set()

    def _serve(self, prompt: str, params: Dict[str, Any]) -> ReplayResponse:
        key = replay_key(self.judge, self.model, self.endpoint, prompt, params)
        for i, line in enumerate(self._lines):
            if i not in self._served and line["key"] == key:
                self._served.add(i)
                if line["outcome"] == "error":
                    name, _, message = line["error"].partition(": ")
                    raise _ERRORS.get(name, RuntimeError)(message)
                return ReplayResponse(line["reply"], line["input_tokens"], line["output_tokens"],
                                      line["cost_usd"], line["model"])
        raise ReplayMissError(
            f"no unused log entry for judge {self.judge}, model {self.model}, key {key[:12]}, "
            f"prompt_sha256 {hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]}")

    def respond(self, prompt: str, **params: Any) -> ReplayResponse:
        return self._serve(prompt, params)

    def chat(self, prompt: str, **params: Any) -> ReplayResponse:
        return self._serve(prompt, params)

    def unused(self) -> List[Dict[str, Any]]:
        return [l for i, l in enumerate(self._lines) if i not in self._served]
