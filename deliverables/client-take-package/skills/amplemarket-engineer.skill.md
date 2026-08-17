# Skill — Amplemarket Engineer
Use when: connecting Amplemarket for contact discovery/enrichment or sequence enrollment.

## Procedure
1. Map Amplemarket's API/model to workspace needs:
   - Discovery: find contacts matching ICP criteria.
   - Enrichment: fill missing contact fields.
   - Sequence enrollment: enroll approved contacts into outreach sequences.
2. Credentials via `ENV:AMPLEMARKET_API_KEY`.
3. Verify scopes are the narrowest set matching the stated capability (scope minimization).
4. Stage enrollment only via the approved Automation Planner path.

## Guardrails
- No secret ever enters artifacts — `ENV:` references only.
- Suppression before any enrollment action.
- Dry-run preview + re-approval on scope/contact-count changes.
