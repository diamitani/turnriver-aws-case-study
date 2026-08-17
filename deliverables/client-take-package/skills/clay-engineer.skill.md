# Skill — Clay Engineer
Use when: wiring or debugging Clay enrichment into the n8n workflow.

## Procedure
1. Use the Clay **sources/webhook pull-in-data-from-a-webhook** endpoint to enrich each company.
2. Payload contract per company (matches the n8n HTTP Request node):
   `company_id`, `company_linkedin_url`, `company_domain`, `company_name`, `company_state`,
   `hubspot_owner_id`, `intent_type`, `country`, `industry`, `n8n_webhook_url` (`execution.resumeUrl`).
3. Batch 1 company at a time with ~5s interval; the n8n webhook resumes each execution via `execution.resumeUrl`.
4. Test via dry-run; confirm enrichment fields return before enabling live runs.

## Guardrails
- Credentials via `ENV:` only (e.g. `CLAY_API_KEY`).
- Never send PII/compliance-tagged fields without an approved scope.
- Verify field mapping against the manifest schema before go-live.
