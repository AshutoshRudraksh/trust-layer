from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


class UntrustedExecutionBlockedError(PermissionError):
    """Raised when untrusted input attempts to trigger an unapproved outbound action or tool call."""


INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+authorized\s+to\s+send", re.IGNORECASE),
    re.compile(r"<\s*/\s*untrusted_data\s*>", re.IGNORECASE),
    re.compile(r"send\s+(an\s+)?(email|slack|message)\s+immediately", re.IGNORECASE),
    re.compile(r"exfiltrate|forward\s+all\s+credentials|reveal\s+api\s+key", re.IGNORECASE),
]


@dataclass(frozen=True)
class IsolatedEnvelope:
    source: str
    wrapped_text: str
    sanitized_content: str
    injection_detected: bool
    matched_signatures: List[str]
    can_trigger_outbound_write: bool = False


class UntrustedDataGuard:
    """
    Wraps external content from emails, webhooks, repositories, and web pages
    inside strict <untrusted_data> tags, нейтралиizes forged closing tags, detects
    prompt injection signatures, and blocks outbound tool or write actions originating
    from untrusted context unless an explicit human approval is granted.
    """

    def wrap(self, raw_text: str, source: str) -> IsolatedEnvelope:
        forged_tag_escaped = re.sub(
            r"<\s*(/?)\s*untrusted_data([^>]*)>",
            r"[ESCAPED_TAG:\1untrusted_data\2]",
            raw_text,
            flags=re.IGNORECASE,
        )
        matched: List[str] = []
        for pattern in INJECTION_PATTERNS:
            if pattern.search(raw_text):
                matched.append(pattern.pattern)

        safe_source = re.sub(r'[^a-zA-Z0-9_.:/-]', "_", source)
        wrapped = (
            f'<untrusted_data source="{safe_source}" trust="untrusted">\n'
            f"{forged_tag_escaped}\n"
            f"</untrusted_data>"
        )
        return IsolatedEnvelope(
            source=safe_source,
            wrapped_text=wrapped,
            sanitized_content=forged_tag_escaped,
            injection_detected=len(matched) > 0,
            matched_signatures=matched,
            can_trigger_outbound_write=False,
        )

    def assert_action_allowed(
        self,
        envelope: IsolatedEnvelope,
        action_type: str,
        target: str,
        explicit_user_approval: bool = False,
    ) -> Dict[str, Any]:
        if not explicit_user_approval:
            reason = (
                f"Outbound action '{action_type}' targeting '{target}' was blocked because "
                f"it originated from untrusted source '{envelope.source}'."
            )
            if envelope.injection_detected:
                reason += f" Prompt injection signatures detected: {envelope.matched_signatures}."
            raise UntrustedExecutionBlockedError(reason)

        return {
            "allowed": True,
            "source": envelope.source,
            "action_type": action_type,
            "target": target,
            "explicit_user_approval": True,
        }
