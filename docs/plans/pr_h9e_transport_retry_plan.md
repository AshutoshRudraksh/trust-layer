Pyx H9e: retry transport errors in post_with_backoff, resume the counted run

## Context

Counted run phase 1, run id pyx_h9_20261102b, started Nov 3, 2026 on merged
main f924eff. It crashed at about 2:03 AM CT after 58 recorded calls, before
the pair naming stop. Cause: a Meta respond call raised httpx.ReadTimeout,
and post_with_backoff in agents/http_retry.py retries only HTTP 429, so the
transport error propagated and the run exited with code 1. The run directory
and log were left untouched; no retry or patch was attempted on the spot.

Ruling (Ashutosh, Nov 3, 2026, on Muse's recommendation, Grok concurring):
fix the retry helper, then resume the same run id. Resume serves finished
steps from the answer store and the call log with zero new calls, so the 58
recorded calls stand, the run's budget_start snapshot and A11 caps stay
coherent, and the crash, the fix, and the resume are disclosed in the counted
run's record PR. A fresh run id was rejected: it would re spend cycle 0 and
orphan this attempt's spend outside the counted caps.

## The change

One module: agents/http_retry.py.

1. post_with_backoff catches httpx.TransportError from the post (ReadTimeout
   is a subclass) and retries it on the same bounded schedule as 429: three
   retries at 1, 2, and 4 seconds, sharing one attempt budget with 429
   retries.
2. When every attempt fails with a transport error, raise a new
   TransportFailedError naming the URL and the exception type only. Headers
   and payload never enter an exception message, as today.
3. Nothing else changes: status error handling, Retry-After handling,
   client timeouts (worker 120 s, judges 40 s), pricing, and the frozen
   EVAL are untouched.

## Tests

Added to evals/test_pyx_clients.py, in the existing MockTransport style:

1. A ReadTimeout twice, then a success, returns the success, with sleeps of
   1 and 2 seconds and three posts seen.
2. A ReadTimeout on every attempt raises TransportFailedError after four
   posts and sleeps of 1, 2, and 4 seconds; the message carries the URL and
   the exception type and no header material.
3. A 429 followed by a transport error followed by a success shares one
   schedule: sleeps of 1 and 2 seconds.

Tests first: the three tests fail against the unmodified helper, then pass
with the fix. Full suite expected at 321 (318 baseline plus 3 new).

## After the merge

1. Grok resumes phase 1 with the recorded command, same run id
   pyx_h9_20261102b, same out directory, PYX_SPEND_LEDGER set to the shared
   ledger.
2. While phase 1 and later phase 2 run, Grok checks on them every 15
   minutes in the chat; a dead run never sits unnoticed again.
3. The counted run's record PR discloses this crash, this fix, and the
   resume, alongside the earlier crashed first start and the H9d fix.

## Departures

None planned. If a departure appears, it is reported in one line as it
happens and named in the PR body.
