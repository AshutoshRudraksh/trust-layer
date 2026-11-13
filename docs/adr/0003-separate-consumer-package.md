# ADR 0003: the consumer is a separate package with an import ban both ways

Status: Decided Nov 12, 2026 by Muse under Ashutosh's delegated authority; Ashutosh may revisit.
Spec: open decision 2 in docs/specs/step1-consumer-agent.md.

## Decision

The consumer lives in its own top level package, `pyx_consumer/`, not inside `pyx/`. A test fails the suite if any module in `pyx_consumer/` imports a `pyx` module other than the MCP client surface it is allowed to use, or if any module in `pyx/` imports `pyx_consumer`. The exact allow list is written in that test when ticket 8 starts.

## Why

The consumer must reach the bank only over MCP, as an outside agent would. An import ban enforced by a test makes a shortcut around the gate fail CI instead of relying on review.

## Consequences

Ticket 8 adds the package and the ban test, failing first.
