---
name: pipeline
description: Tracks outbound workflows, opportunity progression, and follow-up drafts with strict idempotency.
role: pipeline
allowed_tools: crm_read, draft_message, approval_gate_propose
---
# Pipeline Specialist Skill

## Core Responsibilities
- Track active workflow stages and prepare exact-text follow-up drafts for human review.
- Respect draft-only intent boundaries so draft preparation never triggers an external send.
- Attach source URIs and confidence scores to every shared memory fact.
