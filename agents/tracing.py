from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class SpanRecord:
    span_id: str
    trace_id: str
    name: str
    attributes: Dict[str, Any]
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: float = 0.0
    status: str = "OK"


class TraceCollector:
    """
    Lightweight OpenTelemetry-compatible span collector with export metadata
    for Arize Phoenix and LangSmith evaluation runs.
    """

    def __init__(self, project_name: str = "agent-trust-layer") -> None:
        self.project_name = project_name
        self.phoenix_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
        self.langsmith_project = os.getenv("LANGCHAIN_PROJECT", project_name)
        self._spans: List[SpanRecord] = []

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Iterator[SpanRecord]:
        tid = trace_id or f"tr_{uuid.uuid4().hex[:16]}"
        sid = f"sp_{uuid.uuid4().hex[:12]}"
        started_iso = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        span = SpanRecord(
            span_id=sid,
            trace_id=tid,
            name=name,
            attributes=dict(attributes or {}),
            started_at=started_iso,
        )
        try:
            yield span
        except Exception as exc:
            span.status = f"ERROR: {type(exc).__name__}"
            raise
        finally:
            span.duration_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            span.ended_at = datetime.now(timezone.utc).isoformat()
            self._spans.append(span)

    def list_spans(self) -> List[SpanRecord]:
        return list(self._spans)
