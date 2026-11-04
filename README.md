# Pyx

**Every lesson stands trial.**

Pyx is a gate for agent memory. Agents that learn from experience
usually remember whatever they produce, including the wrong lessons,
the lucky ones, and the poisoned ones. Pyx does not let an agent
remember whatever it wants. Every candidate lesson has to earn
admission to the bank, on evidence: graded against a hidden rubric by
two independent judges, tested by causal replay, screened for planted
poison, and approved by a human reading its exact text. What survives
is a bank of earned lessons, each carrying the evidence that admitted
it, that other agents can plug into.

Built for the Meta Global AI Developer Hackathon (Cerebral Valley,
Nov 2026), solo, on Meta models only.

## The counted result

The frozen protocol in EVAL.md was executed end to end on Nov 2 to 3,
2026 (run pyx_h9_20261102b, record in runs/pyx_h9_20261102b/). Eleven
candidate lessons were distilled; exactly one earned admission. Cycle
1 then compared four arms on criterion pass rate (conclusive
criteria):

| Arm | Pass rate |
| --- | --- |
| earned_lessons (the 1 earned lesson) | 0.625 |
| free_lessons (all 11, unfiltered) | 0.5208 |
| no_memory | 0.4375 |
| raw_traces | 0.4375 |

Paired bootstrap 95% CIs on the earned arm's advantage exclude zero
against every arm (free +0.104 [+0.021, +0.229], no memory +0.188
[+0.146, +0.229], raw traces +0.188 [+0.125, +0.271], over 6 paired
task and repetition cells). The planted poison run earned nothing.
The full record, including every failure and interruption the run
survived, is in runs/pyx_h9_20261102b/RESULTS.md, and the whole run
reruns keyless from its own call log (see Quickstart).

## How it works

1. **Answer.** A worker answers rubric tasks over research papers
   (Reflexion and Agentless for training; the held out set is out of
   the counted run).
2. **Grade.** A programmatic checker scores 7 criteria; two judges
   score the eighth, which demands the authors' own explanation. A
   criterion fails only when both judges agree it fails.
3. **Distill.** Candidate lessons are distilled from the graded
   failures. The distiller never sees check text, expected values, or
   judge replies.
4. **Poison check.** Candidates from a source carrying planted
   instructions or a planted false claim must not carry that content,
   verbatim or paraphrased.
5. **Paired replay.** Each candidate is replayed against its task:
   it must fix its target criterion in at least 2 of 3 repetitions
   and break nothing in any.
6. **Human gate.** A person approves or denies the exact lesson
   text. No approval, no admission, whatever the scores say.
7. **Bank.** Earned lessons, with their verdict records, form the
   bank. Retrieval for this horizon is all earned lessons in context,
   and the bank is served read only over MCP (below).

## Meta models

Every model called at runtime is a Meta model, fallbacks included.

| Role | Model | Where it runs |
| --- | --- | --- |
| Worker, distiller, Judge A | muse-spark-1.3-contributor | Meta Model API |
| Judge B | muse-spark-open-1026 | Baseten |

Judge B runs on Baseten's meta-models/muse-spark-open-1026 endpoint:
Muse Spark Open, Meta's open weight model, is the second judge, and
it is load bearing. No lesson is earned unless the open weight judge
also passes it, and the counted run's verdicts were produced with it.

## Quickstart

Python 3.11 or newer. No key is needed for the test suite, the frozen
protocol check, or rerunning the counted run.

```bash
pip install -e ".[dev,mcp]"
pytest
python -m pyx.run check-eval --eval-sha256 73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb
```

Rerun the counted run keyless from its committed record (no keys, no
spend; decisions and metrics reproduce byte for byte):

```bash
SRC=runs/pyx_h9_20261102b
SHA=73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb
python -m pyx.run phase1 --run-id pyx_h9_20261102b --out /tmp/rerun --eval-sha256 $SHA --reps 3 --keyless --from $SRC
python -m pyx.run phase1 --run-id pyx_h9_20261102b --out /tmp/rerun --eval-sha256 $SHA --reps 3 --pairs $SRC/pairs.txt --keyless --from $SRC
grep -P "\tapproval\t" $SRC/decisions.tsv >> /tmp/rerun/decisions.tsv
python -m pyx.run phase2 --run-id pyx_h9_20261102b --out /tmp/rerun --eval-sha256 $SHA --reps 3 --keyless --from $SRC
diff $SRC/decisions.tsv /tmp/rerun/decisions.tsv
diff $SRC/metrics.json /tmp/rerun/metrics.json
```

To run live, supply your own keys (never commit them):

```bash
export MODEL_API_KEY=<your Meta Model API key>
export BASETEN_API_KEY=<your Baseten API key>
```

A live phase also needs a shared spend ledger file, and refuses to
start without one. Create it first and point the run at it:

```bash
echo '{"version": 1, "providers": {}}' > ~/pyx-ledger.json
export PYX_SPEND_LEDGER=~/pyx-ledger.json
```

With no key set, nothing is called: the pipeline's keyless mode
replays recorded calls, and the scaffold client falls back to a
deterministic dry run. Neither path reaches a model.

## Inspect the bank over MCP

The counted run's bank is served by a read only MCP server with
exactly two tools: query earned lessons by task family or criterion,
and fetch a lesson's provenance and verdict record.

```bash
python -m pyx.mcp_server --run-dir runs/pyx_h9_20261102b
```

Streamable HTTP on 127.0.0.1:8377 by default. There are no write
tools; the bank changes only through the pipeline and the human gate.

## What existed before, what was built this week

This repository began the event week as a trust layer scaffold:
Meta and Baseten clients with a persistent spend ledger, an approval
gate pattern, and isolation utilities. Pyx, the gated memory
experiment that is this submission, was designed and built on top of
it during the event: the frozen EVAL.md protocol, the grading and
judging pipeline, the distiller, the poison screen, paired replay,
engine, and the MCP bank server. The scaffold's first commit landed
on October 26 at 11:26 AM CT, shortly before the organizer notice's
listed event start of 12:00 PM CT that day. Everything else in this
repository, including all of Pyx, was written during the event. The
surrounding scaffold (api/,
gate/, locks/, room/) is context the experiment plugs into, not the
submission itself.

## Repository layout

- `pyx/`: the Pyx pipeline (grading, judges, distill, replay, phases,
  the bank, the MCP server).
- `EVAL.md`: the frozen evaluation protocol. Runs count only against
  its recorded sha256.
- `runs/`: the pilot record (runs/pilot_thin_20261102_r1/) and the
  counted run record (runs/pyx_h9_20261102b/), with results and
  disclosures.
- `evals/`: the test suite.
- `agents/`: the Meta and Baseten clients and the spend ledger.
- `docs/plans/`: the plan file governing each pull request.

## License

MIT (declared in pyproject.toml).
