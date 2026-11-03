# Pyx H9d: phase engine calls each live client through its real method

Status: DRAFT plan for Ashutosh. Base: main d9a8f02 (EVAL.md sha256 73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb). Branch: pyx/h9d-live-seam. No repo code changed, nothing pushed, no API calls. The failing output below comes from an uncommitted scratch copy of main.

## 1. The bug, read from main
- `pyx/phase.py` lines 54 to 61: `LogFirst.respond` serves from `ReplayClient.respond`, else `RecordingClient.respond`; line 63 `chat = respond` routes every `chat` call to `respond`.
- `pyx/judges.py` lines 79 to 88 (`_ask`): Judge A calls `client.respond(prompt, role="eval-runner", reasoning_effort=..., max_output_tokens=..., temperature=...)`; Judge B calls `client.chat(prompt, max_tokens=MAX_OUTPUT_TOKENS, temperature=TEMPERATURE)`.
- So Judge B goes `LogFirst.chat` (alias of respond), `RecordingClient.respond`, then `getattr(BasetenClient, "respond")`, which does not exist. `BasetenClient` public methods: `chat`, `estimate_cost_usd` (agents/baseten_client.py line 84 is `chat`).
- `ReplayClient` (pyx/replay_client.py lines 59 to 63) and `RecordingClient` (pyx/recording.py lines 53 to 57) already expose both methods and pass the method name through. Only the phase wrapper collapses them.
- The test `Fake` (evals/test_pyx_phase1.py line 18) defines `respond` plus `chat = respond`, so it accepts both and 307 tests passed.

## 2. Ruling 1: fix at the phase boundary
- In `LogFirst`, delete `chat = respond`. Add `_serve(method, prompt, params)` that calls `getattr(self.replay, method)` and on `ReplayMissError` `getattr(self.live, method)`. `respond` calls `_serve("respond", ...)`, `chat` calls `_serve("chat", ...)`. Keyword arguments pass through unchanged, so Judge B keeps `max_tokens` and `temperature` exactly as judges.py sends them.
- `agents/baseten_client.py` is not touched. No `respond` alias is added there. The respond versus chat split stays where judges.py keeps it.
- Replay keys are built from judge, model, endpoint, prompt and params (replay_client.py line 46), not from the method name, so keyless replay of earlier logs is unaffected.

## 3. Ruling 2: tests first
New file `evals/test_pyx_phase_seam.py` (draft copy at /workspace/pyx-drafts/h9d_test_pyx_phase_seam_draft.py):
1. `test_engine_calls_judge_b_through_chat_with_max_tokens_and_temperature`: a `ChatOnlyBaseten` fake with only `chat` and `estimate_cost_usd`; `Engine(...).c["b"].chat("judge prompt", max_tokens=2048, temperature=0)` must reach the fake's `chat` with those two values.
2. `test_phase1_runs_cycle0_with_a_chat_only_judge_b`: `phase1` with the chat only fake as `b` returns 0 and Judge B was called through `chat`.
3. Conformance: one assertion over every phase test fake that its public callable set equals the real client's public callable set.

Fake to real client map, read from the tests:
| Fake | Where | Stands for | Real public methods |
|---|---|---|---|
| `Fake` as `worker` | test_pyx_phase1 `_live`, test_pyx_phase2 | `MetaModelClient` via `pyx.worker.worker_client` (run.py line 173) | `build_responses_payload`, `estimate_cost_usd`, `respond` |
| `Fake` as `a` and `distill` | same | `MetaModelClient` | same |
| `Fake` as `b` | same | `BasetenClient` | `chat`, `estimate_cost_usd` |
| `_PoisonFake` (subclass of `Fake`) | test_pyx_phase2 line 133 | same four roles | same |
| `Ledger` | test_pyx_phase1 line 38 | `SpendLedger` | `record`, `snapshot`, `total_usd` |

Today `Fake` exposes `chat`, `respond`, which equals neither real set (checked: `==Meta False`, `==Baseten False`). The fix splits it into `MetaFake` (respond, with `build_responses_payload` and `estimate_cost_usd` stubs that raise if called) and `BasetenFake` (chat, with an `estimate_cost_usd` stub), shares one call recorder so call count assertions keep working, and makes `_PoisonFake` subclass `MetaFake` (it only alters distill replies). `_live` returns the split fakes. The conformance test parametrizes over (MetaFake, MetaModelClient), (BasetenFake, BasetenClient), (_PoisonFake, MetaModelClient), (ChatOnlyBaseten, BasetenClient), and, open question 2, (Ledger, SpendLedger).

Meta path check: every Meta call in the phase path uses `respond` (worker_run.py line 73, distill.py line 76, judges.py line 81), and `MetaModelClient` has `respond` and no `chat`. No live mismatch there. The only latent risk on the Meta side is the same class: `Fake` also offers `chat`, so a future `chat` call on a Meta role would pass tests and fail live. The conformance assertion closes that.

Failing output captured on unmodified main (scratch copy, not committed):
```
pyx/judges.py:88: in _ask
pyx/phase.py:61: in respond
pyx/recording.py:54: in respond
kwargs = {'max_tokens': 2048, 'temperature': 0}
>           resp = getattr(self._inner, method)(prompt, **kwargs)
E           AttributeError: 'ChatOnlyBaseten' object has no attribute 'respond'
pyx/recording.py:42: AttributeError
FAILED evals/test_pyx_phase_seam.py::test_engine_calls_judge_b_through_chat_with_max_tokens_and_temperature
FAILED evals/test_pyx_phase_seam.py::test_phase1_runs_cycle0_with_a_chat_only_judge_b
2 failed, 1 passed in 0.24s
```
This is the same AttributeError and the same frames as the live crash. The passing test is the fake's own surface check. With only the section 2 change applied in the scratch copy: `3 passed`, and the full suite read `310 passed` (307 plus 3). The fake split and ledger tests are not yet run; the expected final count is stated at the gate.

## 4. Ruling 3: fresh run id, crashed attempt kept
- New run id: `pyx_h9_20261102b`, out dir `runs/pyx_h9_20261102b` in a fresh clone of the merged main.
- The crashed attempt `pyx_h9_20261102` stays where it is: /workspace/h9v/runs/pyx_h9_20261102/ (`calls.jsonl` 3 lines: worker $0.0023057, checker $0, Judge A $0.0003785; `answers.jsonl`; `budget_start.json` reading meta 0.0, baseten 0.0), the clone ledger /workspace/h9v/runs/spend_ledger.json (meta $0.0026842, 2 call ids, no baseten), and the console /workspace/phase1_pyx_h9_20261102.log. Before the counted run I copy all four, unchanged, to /workspace/pyx-drafts/crashed_pyx_h9_20261102/ with a sha256 list. The run report has a section naming it, its 3 calls, its spend and the crash line.

## 5. Ruling 4: shared ledger, real cumulative stop
Facts from main:
- `SpendLedger()` with no path reads `PYX_SPEND_LEDGER`, else `REPO_ROOT/runs/spend_ledger.json` (agents/spend_ledger.py lines 21 to 28). `pyx/run.py` line 171 calls `SpendLedger()`, so a fresh clone gets its own empty ledger unless the env var is set. That is how the crashed run's $0.0026842 landed in /workspace/h9v/runs/spend_ledger.json.
- The shared ledger used by the pilot is /workspace/trust-layer/runs/spend_ledger.json: meta $0.108977 (99 calls), baseten $0.35406425 (56 calls), matching the pilot figures.
- Two different stops exist. (a) The A11 caps in `Engine.check_budget` (phase.py lines 79 to 90) compare `ledger.total_usd(p) - budget_start[p]` to $0.80 Meta and $2.50 Baseten. That is per run new spend, written once to `budget_start.json` in the run's out dir, so it spans phase 1, the pairs resume and phase 2 of one run id. This matches the frozen wording "new Meta spend passes $0.80". (b) The cumulative hard stop is in the clients: `MetaModelClient` refuses a call whose projection passes the $40 `DEFAULT_BUDGET_CAP_USD` on the ledger total (meta_client.py lines 124, 175 to 186). That stop is only real if the ledger is the shared one.
- Today only the command enforces the shared ledger (by the env var). Nothing in code refuses an empty clone ledger.

Plan:
- Reconcile first, as a separate step before the run: for each of the two meta call ids in the clone ledger, `SpendLedger("/workspace/trust-layer/runs/spend_ledger.json").record("meta", call_id, cost)`, with costs 0.0023057 and 0.0003785 taken from calls.jsonl in seq order. `record` ignores a repeated id, so this is idempotent. Expected shared meta total $0.1116612, 101 calls; baseten unchanged. Shown as before and after snapshots. Open question 3 covers the id to cost pairing.
- Code guard (small, in pyx/run.py `_phase1`): a live phase1 or phase2 refuses with exit 2, before any call, unless `PYX_SPEND_LEDGER` is set and names an existing file. Test written first: live invocation without the env var exits 2 and the fake records zero calls.
- Report: at every stop (awaiting pairs, ready for approval, abort, phase 2 end) the engine prints and writes `spend.json` with per provider `start`, `now`, `run_delta` and `cumulative`. Test written first with the fake ledger: the line shows delta equal to fake spend and cumulative equal to start plus delta.
- No change to A11 semantics in this package: caps stay per run deltas exactly as frozen.

## 6. Files to touch
| File | Change | Lines (est) |
|---|---|---|
| pyx/phase.py | `LogFirst` method dispatch; spend report at stops | about 20 |
| pyx/run.py | shared ledger guard | about 8 |
| evals/test_pyx_phase1.py | split `Fake` into `MetaFake` and `BasetenFake`, shared recorder | about 30 |
| evals/test_pyx_phase2.py | `_PoisonFake` base change, imports | about 5 |
| evals/test_pyx_phase_seam.py | new: seam tests, conformance, ledger guard, spend report | about 90 |
Estimated total about 150 lines, one PR. agents/ is not touched.

## 7. Spend
Package: $0. All tests use fakes and need no keys. The reconcile step moves recorded spend between ledgers and makes no calls. Counted run spend stays inside the frozen estimate (about $0.37 Meta, $1.08 Baseten) and A11 caps.

## 8. Counted run command (after H9d merges and my fresh clone check)
```
export PYX_SPEND_LEDGER=/workspace/trust-layer/runs/spend_ledger.json
python -m pyx.run phase1 --run-id pyx_h9_20261102b --out runs/pyx_h9_20261102b --eval-sha256 73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb --reps 3
```
It stops at awaiting pairs for Ashutosh. Keys come from environment variables only.

## 9. Open questions with defaults
1. Run id. Default `pyx_h9_20261102b`.
2. Conformance scope: include the `Ledger` fake against `SpendLedger` (adds `record` and `snapshot` stubs). Default: yes, it is a phase test fake standing for a real object.
3. Reconcile pairing: the clone ledger stores call ids without costs; I pair them to calls.jsonl costs in order. Default: pair in order and show the sum equals $0.0026842.
4. A11 and the crashed attempt: does its $0.0026842 count toward this run's $0.80 Meta cap? Default: no; caps are per run new spend as frozen, and the crashed spend shows in the cumulative total. If you want it counted, that is an EVAL amendment for your ruling.
5. Shared ledger enforcement: code guard (default) versus command only.
6. Crashed attempt preservation: box copy under /workspace/pyx-drafts (default) versus also committing it under runs/ in the report PR.
