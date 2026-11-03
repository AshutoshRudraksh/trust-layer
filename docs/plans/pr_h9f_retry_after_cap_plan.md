Pyx H9f: cap the Retry-After wait in post_with_backoff

## Context

Counted run phase 1, run id pyx_h9_20261102b, resumed Nov 3, 2026 on main
a2c408d, stalled twice in one day with the same signature: the process alive,
almost no CPU used, no error, and no log writes for long stretches (44
minutes, then again 7 minutes and counting after a stop and resume that
reused all 205 recorded calls). Both stalls sat on Meta judge calls.

Code inspection rules out a hanging request: every client carries an httpx
timeout (40 s judges, 120 s worker), and since H9e a timeout retries and
raises within minutes. The one unbounded wait in the call path is the 429
branch of post_with_backoff in agents/http_retry.py: it sleeps for the
server's Retry-After value, parsed as a float, with no cap. A 429 carrying a
large Retry-After produces exactly the observed signature, and the sleep
leaves no trace in the call log because the call has not returned. The
Retry-After value itself was never observed, which is part of the defect:
an hours long server controlled sleep inside a timed run is invisible.

## The change

One module: agents/http_retry.py.

1. The honored Retry-After wait is capped at MAX_RETRY_AFTER_S, 60 seconds.
   A server asking for less is honored exactly as today; a server asking
   for more gets 60 seconds per attempt, and the existing attempt budget
   (three retries) still applies, so a persistent long rate limit ends in
   RateLimitedError, loudly, inside about three minutes, instead of
   sleeping silently for an unbounded time.
2. The cap lives in _retry_after_seconds, so the function returns the
   seconds to wait and the call site is unchanged.
3. Nothing else changes: transport retries (H9e), status handling, client
   timeouts, pricing, and the frozen EVAL are untouched.

## Tests

Added to evals/test_pyx_clients.py, in the existing MockTransport style:

1. A 429 with Retry-After 3600 followed by a success returns the success
   with one sleep of exactly 60 seconds.
2. A 429 with Retry-After 3600 on every attempt raises RateLimitedError
   after four posts with sleeps of 60, 60, and 60 seconds.

The existing Retry-After test (7 seconds honored verbatim) already pins the
under cap behavior and must keep passing. Tests first: the two new tests
fail against the unmodified helper, showing sleeps of 3600. Full suite
expected at 323 (321 baseline plus 2 new).

## After the merge

1. Grok stops the stalled phase 1 process if it is still sleeping, then
   resumes phase 1 with the recorded command, same run id
   pyx_h9_20261102b, same out directory, PYX_SPEND_LEDGER set to the shared
   ledger. The 205 recorded calls are reused; nothing is repeated.
2. The counted run's record PR discloses both stalls, this diagnosis, and
   this fix, alongside the earlier crashes and fixes.

## Departures

None planned. If a departure appears, it is reported in one line as it
happens and named in the PR body.
