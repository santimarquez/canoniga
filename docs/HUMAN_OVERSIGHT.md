# Human Oversight

## Review gates

Canoniga enforces human oversight through:

- **Review flags** for high confidence drift or contradiction density
- **Signoff requirements** for hypothesis promotion when enabled
- **Investigation run approval** when quality gates fail
- **Causal-risk guardrail** blocking fact labels under high contradiction density

## Investigator responsibilities

1. Validate cited claim IDs against source records before acting on synthesis
2. Resolve review queue items before promoting hypotheses to downstream workflows
3. Treat automation outputs as drafts requiring scientific judgment

## Escalation policy

Escalate to a senior reviewer when:

- Causal-risk guardrail blocks a high-priority entity
- Failure atlas shows repeated root-cause recurrence for the same target class
- Freshness alarms persist for more than 48 hours

## Auditability

- User activity timeline: `GET /api/auth/audit`
- Review decisions persisted in `review_decisions`
- Investigation run history with quality-gate checks and replay diffs

## Automation handoff

When `approval_status=pending` on failed quality gates, automation must not auto-promote results. Human approval is required before treating run output as canonical.
