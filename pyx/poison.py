"""The poison check (spec Section 5): a lesson whose source is document text is rejected as UNTRUSTED_SOURCE.

It does not trust the distiller's own source_kind stamp. A candidate fails when
any one rule fires, checked in this order:
  provenance: its provenance says document_text;
  span: its text shares SPAN_WORDS or more consecutive normalized words with the
        paper text of its source task;
  signature: isolation/untrusted_guard.py finds an injection signature in its text.
The caller hands in the paper text. This module reads no file and makes no model
call, and it knows nothing about any test material, so it cannot be tuned to it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from isolation.untrusted_guard import UntrustedDataGuard
from pyx.lessons import Candidate

SPAN_WORDS = 8
UNTRUSTED_SOURCE = "UNTRUSTED_SOURCE"
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class PoisonVerdict:
    lesson_id: str
    passed: bool
    reason_code: str  # UNTRUSTED_SOURCE on a fail, empty on a pass
    rule: str  # provenance, span or signature on a fail, empty on a pass
    detail: str  # the matched span or signatures, for the report


def normalize_words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def shared_span(lesson_text: str, paper_text: str, n: int = SPAN_WORDS) -> str:
    """The first run of n consecutive normalized lesson words that also occurs in the paper, or ""."""
    paper = normalize_words(paper_text)
    grams = {tuple(paper[i:i + n]) for i in range(len(paper) - n + 1)}
    words = normalize_words(lesson_text)
    for i in range(len(words) - n + 1):
        if tuple(words[i:i + n]) in grams:
            return " ".join(words[i:i + n])
    return ""


def check_candidate(candidate: Candidate, paper_text: str) -> PoisonVerdict:
    lid, text = candidate.lesson.lesson_id, candidate.lesson.text

    def fail(rule: str, detail: str) -> PoisonVerdict:
        return PoisonVerdict(lid, False, UNTRUSTED_SOURCE, rule, detail)

    if candidate.provenance.source_kind == "document_text":
        return fail("provenance", "source_kind document_text")
    span = shared_span(text, paper_text)
    if span:
        return fail("span", span)
    envelope = UntrustedDataGuard().wrap(text, source=f"lesson:{lid}")
    if envelope.injection_detected:
        return fail("signature", "; ".join(envelope.matched_signatures))
    return PoisonVerdict(lid, True, "", "", "")
