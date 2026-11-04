"""HTTP POST with backoff, shared by the Meta and Baseten clients.

Retries cover HTTP 429 and transient transport errors (httpx.TransportError,
which includes read timeouts and connection errors) on one shared schedule:
three retries at 1, 2 and 4 seconds. A numeric Retry-After header replaces
the scheduled wait after a 429, capped at MAX_RETRY_AFTER_S: a server may
ask for a shorter wait, never for an unbounded one. Every attempt also runs
under a hard wall clock deadline of ATTEMPT_DEADLINE_S, enforced above the
transport on a daemon thread: an attempt still running at the deadline
counts as a transport failure on the same schedule, so a connection whose
headers never arrive can no longer hang a run past the deadline, whatever
the transport's own timeout machinery does. Errors name the URL, the
status, and the transport error type only, never request headers, so an
API key cannot leak through an exception message.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Sequence

import httpx

BACKOFF_SCHEDULE_S: Sequence[float] = (1.0, 2.0, 4.0)

MAX_RETRY_AFTER_S: float = 60.0

ATTEMPT_DEADLINE_S: float = 300.0


class RateLimitedError(RuntimeError):
    """Raised when every retry still returned HTTP 429."""


class TransportFailedError(RuntimeError):
    """Raised when every attempt failed with a transport error."""


class AttemptDeadlineError(RuntimeError):
    """Raised when one attempt is still running at its wall clock deadline."""


def _retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return min(MAX_RETRY_AFTER_S, max(0.0, float(raw)))
    except ValueError:
        return None


def _post_once(
    client: httpx.Client,
    url: str,
    headers: Dict[str, str],
    json: Dict[str, Any],
    deadline_s: float,
) -> httpx.Response:
    box: Dict[str, Any] = {}

    def go() -> None:
        try:
            box["resp"] = client.post(url, headers=headers, json=json)
        except BaseException as exc:  # re-raised on the caller thread below
            box["err"] = exc

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    thread.join(deadline_s)
    if thread.is_alive():
        raise AttemptDeadlineError(f"attempt still running after {deadline_s} seconds")
    if "err" in box:
        raise box["err"]
    return box["resp"]


def post_with_backoff(
    client: httpx.Client,
    url: str,
    headers: Dict[str, str],
    json: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
    schedule: Sequence[float] = BACKOFF_SCHEDULE_S,
    deadline_s: float = ATTEMPT_DEADLINE_S,
) -> httpx.Response:
    for attempt in range(len(schedule) + 1):
        try:
            resp = _post_once(client, url, headers, json, deadline_s)
        except (httpx.TransportError, AttemptDeadlineError) as exc:
            if attempt == len(schedule):
                raise TransportFailedError(
                    f"transport error from {url} after {len(schedule)} retries: {type(exc).__name__}"
                ) from exc
            sleep(schedule[attempt])
            continue
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        if attempt == len(schedule):
            break
        wait = _retry_after_seconds(resp)
        sleep(wait if wait is not None else schedule[attempt])
    raise RateLimitedError(f"HTTP 429 from {url} after {len(schedule)} retries")
