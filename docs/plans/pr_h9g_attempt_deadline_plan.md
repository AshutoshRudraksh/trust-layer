# PR H9g plan: a hard wall clock deadline for every HTTP attempt

Status: proposed by Muse under the Nov 3, 2026 seat split. Grok commits
verbatim and reviews as critic; Ashutosh approves and merges. Ruled Nov 3,
2026 as fix work that gates the counted run record and all submission work.

## Why

The counted run stalled three times inside a single HTTP attempt: a Meta
worker call whose response headers never arrived (py spy showed the process
parked in SSLSocket.recv during replay), with the client's own read timeout
never firing. H9e taught post_with_backoff to retry transport errors and H9f
capped the Retry-After wait, but nothing bounds one attempt itself. A
watchdog absorbed the stalls operationally; the defect class stays open
until the deadline lives in the code, above the socket layer, independent
of whatever timeout machinery failed underneath.

## What changes

- agents/http_retry.py only, plus tests. post_with_backoff gains a
  deadline_s parameter defaulting to ATTEMPT_DEADLINE_S, 300 seconds. Each
  attempt's client.post runs on a daemon thread; the caller waits at most
  deadline_s for it. An attempt still running at the deadline raises
  AttemptDeadlineError, which joins the existing transport failure path:
  the same 1, 2, 4 second schedule, the same shared attempt budget, and
  TransportFailedError naming the URL and the error type when the budget
  runs out. The abandoned thread is left to the operating system; the
  caller never joins it again.
- Why 300: the slowest completed call in the counted run took 155.2
  seconds (a worker call, from the run's own calls.jsonl). The deadline
  sits at roughly twice that, so it can only fire when the transport's own
  timeout machinery has failed, never on a slow but healthy call. The
  stalls it kills lasted 20 minutes and longer.
- No client changes: both call sites keep calling post_with_backoff as
  today and inherit the default deadline. The frozen EVAL, the retry
  schedule, the Retry-After cap, and the error hygiene (no headers in
  messages) are untouched.

## Tests first

Three tests appended to evals/test_pyx_clients.py, against the existing
MockTransport helpers:

1. A first attempt that hangs for 2 seconds is abandoned at a 0.2 second
   deadline, retried on the schedule, and the second attempt succeeds; the
   whole call returns in well under the hang time.
2. A transport that always hangs exhausts the shared budget: 4 attempts,
   sleeps 1, 2, 4, then TransportFailedError naming the URL and
   AttemptDeadlineError, with no header value in the message.
3. An attempt that answers inside the deadline returns untouched: one
   attempt, no sleeps.

## Live test

- Fresh clone of the PR head: the full suite passes (329 baseline plus
  the 3 new tests) and check-eval exits 0 with the frozen hash.
- The authoring run executes the same numbers in the build clone before
  the package ships.

## Boundaries

One function changes; no new dependencies (threading is stdlib). A
deadline expiry mid 429 sequence shares the one budget, exactly like the
transport errors H9e unified. Process exit does not wait for an abandoned
attempt: daemon threads die with the process, which is the documented
trade for never hanging again.
