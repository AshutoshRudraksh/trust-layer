"""HTTP POST with backoff on 429, shared by the Meta and Baseten clients.

Three retries at 1, 2 and 4 seconds. A numeric Retry-After header replaces the
scheduled wait. Errors name the URL and status only, never request headers, so
an API key cannot leak through an exception message.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Sequence

import httpx

BACKOFF_SCHEDULE_S: Sequence[float] = (1.0, 2.0, 4.0)


class RateLimitedError(RuntimeError):
    """Raised when every retry still returned HTTP 429."""


def _retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def post_with_backoff(
    client: httpx.Client,
    url: str,
    headers: Dict[str, str],
    json: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
    schedule: Sequence[float] = BACKOFF_SCHEDULE_S,
) -> httpx.Response:
    for attempt in range(len(schedule) + 1):
        resp = client.post(url, headers=headers, json=json)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        if attempt == len(schedule):
            break
        wait = _retry_after_seconds(resp)
        sleep(wait if wait is not None else schedule[attempt])
    raise RateLimitedError(f"HTTP 429 from {url} after {len(schedule)} retries")
