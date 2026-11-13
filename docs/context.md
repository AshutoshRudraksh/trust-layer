# Context

Pyx is a layer other agents plug into, not another agent: graded sleep for agent memory. Lessons are distilled from graded failure traces, screened for poison, replayed causally, and admitted to a bank only after Ashutosh approves the exact text. The bank is served read only over MCP (pyx/mcp_server.py).

## Fixed points

- Judged state: tag hackathon-judged-f97708e on commit f97708ec03c6ad2510f69497c2d7eb370bc7d431. Never moved or retagged.
- Frozen eval: EVAL.md, sha256 73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb, checked by `python -m pyx.run check-eval`.
- Counted run: runs/pyx_h9_20261102b, immutable.
- Suite at f97708e: 336 passed, no keys needed.

## Where things live

- Admission chain: pyx/poison.py, pyx/replay.py, pyx/approval.py over gate/approval_gate.py.
- Records: decisions.tsv (docs/decisions_tsv.md), candidates files, call logs for keyless replay.
- Bank and MCP read path: pyx/bank.py, pyx/mcp_server.py.
- Plans for merged work: docs/plans/. Specs for new work: docs/specs/. Decisions: docs/adr/, numbered.

## Specs

- docs/specs/step1-consumer-agent.md: a second agent that consumes the bank over MCP, with gated write back.

## Decisions

- docs/adr/0001-gated-consumer-read-path.md
