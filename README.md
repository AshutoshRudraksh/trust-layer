# Trust Layer

Trust Layer is an open-source, trust-first multi-agent execution runtime powered by the Meta Model API. It gives engineering and operations teams a verifiable control plane for specialist AI agents with exact-text approval gates, deterministic idempotency, untrusted input isolation, single-owner task locks, sourced and user-correctable memory, and anti-spam durable routines.

## Problem Statement

Modern multi-agent systems fail in production when moving from read-only chat to external actions. Teams encounter four recurring reliability and security failures:

1. **Prompt Injection on Untrusted Inputs:** External emails, webhooks, pull requests, and web pages can inject instructions that trick agents into unauthorized outbound writes.
2. **Duplicate External Writes on Retries:** Worker restarts or network timeouts cause agents to send duplicate emails, messages, or tickets.
3. **Multi-Agent Race Conditions and Notification Spam:** Multiple specialist agents act on the same thread or issue simultaneously and flood users with repetitive nudges.
4. **Opaque Memory Drift:** Unverified facts enter shared memory without source attribution, and user corrections fail to update agent behavior.

Trust Layer resolves all four challenges in a unified execution layer.

## Architecture and Repository Layout

* `api/`: FastAPI service exposing `/health`, `/actions/propose`, `/approvals/{approval_id}/decide`, `/approvals/{approval_id}/execute`, `/locks`, `/locks/claim`, `/memory/facts`, `/memory/correct`, and `/room/priority-list`.
* `gate/`: `ApprovalGate` enforcing exact-text previews, unified diffs (`difflib.unified_diff`), deterministic SHA-256 idempotency keys, draft-only send blocking, hard denial locks until a new user instruction ID is issued, and an append-only SQLite audit log.
* `locks/`: `OwnerRegistry` providing single-owner task locks so specialist agents serialize cleanly and route secondary context to the Priority Room with zero duplicate nudges.
* `isolation/`: `UntrustedDataGuard` wrapping external text in `<untrusted_data>` tags, escaping forged closing tags, detecting prompt injection signatures, and blocking unapproved outbound writes.
* `agents/`:
  * `meta_client.py`: OpenAI-compatible Meta Model API client (`https://api.meta.ai/v1/responses` and `/v1/chat/completions`) routing specialist agents (`chief-of-staff`, `pipeline`, `research`, `code-review`) to `muse-spark-1.3` with validated reasoning effort (`low`, `medium`, `high`, `max`) and background memory consolidation and evaluations to `muse-spark-1.3-contributor`, backed by a strict $150.00 credit cap ledger.
  * `skills_loader.py` and `skills/*/SKILL.md`: Progressive Agent Skills loader that parses YAML frontmatter at startup, loads full skill bodies on demand, and generates reviewed unified diffs when user corrections update agent rules.
  * `tracing.py`: Span collector compatible with Arize Phoenix and LangSmith tracing.
* `memory/`: `MemoryStore` storing shared facts with mandatory `source_uri`, `timestamp`, and `confidence`, converting user corrections into reviewed unified diffs against the responsible agent's `SKILL.md`.
* `workflows/`: `RoutineCooldownRunner` enforcing 24-hour anti-spam nudge cooldowns per routine and target item.
* `room/`: `PriorityRoomMerger` and React TypeScript UI (`room/ui/PriorityRoom.tsx`) consolidating pending approvals, active task locks, and specialist findings into one ranked view.
* `evals/`: Automated red-team and reliability test suite (`evals/test_day1_suite.py`).

## Quickstart

### 1. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure Meta Model API Credentials

```bash
export MODEL_API_KEY="your_meta_model_api_key"
```

When `MODEL_API_KEY` is omitted, `MetaModelClient` runs in deterministic local dry-run mode while still enforcing reasoning validation and the $150.00 budget guard.

### 3. Run the Evaluation and Test Suite

```bash
pytest -v
```

### 4. Start the API Server

```bash
uvicorn api.main:app --reload --port 8000
```

## Verified Guarantees

1. **Idempotent Execution:** Forced retries on an approved action execute the underlying side effect exactly once.
2. **Hard Denial Lock:** Denied actions remain locked against re-proposal or execution until a new user instruction ID is provided.
3. **Draft-Only Send Blocking:** Any external send action proposed under `intent="draft"` is rejected at the gate and recorded in the audit log.
4. **Untrusted Input Isolation:** Prompt injection payloads inside external data cannot close `<untrusted_data>` fences or trigger outbound writes.
5. **Single-Owner Task Serialization:** Concurrent lock claims by multiple specialist agents never produce duplicate nudges; secondary context is merged into the Priority Room.
6. **Budget Guard Enforcement:** Uncredited accounts or requests exceeding the $150.00 cap are blocked before invoking the Meta Model API.
