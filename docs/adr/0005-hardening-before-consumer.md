# ADR 0005: hardening first, consumer after

Status: Decided Nov 12, 2026 by Muse under Ashutosh's delegated authority; Ashutosh may revisit.
Spec: open decision 4 in docs/specs/step1-consumer-agent.md.

## Decision

Land Hackathon Builder's hardening items before the consumer, one ticket each, in this order:

1. Poison screen positive control: a test that a known poisoned lesson is rejected.
2. One held out transfer task.
3. Counted ledger in CI: dash check and README suite count.
4. Chart generated from runs/pyx_h9_20261102b/RESULTS.md, with a test that the chart and the file agree.
5. Rerunnable live test scripts.

Then the consumer tickets.

## Why

The consumer builds on the bank's claims. Each hardening item checks one of those claims, so a hole found there is found before anything depends on it.

## Consequences

The ticket list in the spec is renumbered: hardening is tickets 3 to 7, the consumer is tickets 8 to 11.
