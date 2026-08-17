# Skill — n8n Engineer
Use when: building, versioning, or debugging the n8n workflow (the daily outreach engine).

## The engine (existing "Prospect Automation — Part 1" workflow)
```
Schedule Trigger (07:00) → Set Yesterday Range (code)
→ Get HubSpot Companies (intent/ABM workflow-date in range; search API)
→ Split Each Company → Filter remove APAC → Less than 2,000 employees
→ Remove competitors (Deel/Remote/Rippling) → Filter 0 associated deals
→ Filter lifecycle ≠ customer → Filter type ≠ Customer → Filter last sales activity > 30d
→ ICP Filter (Schools & Gov) → Round Robin Assignment (code) → Edit Fields
→ HTTP → Clay webhook (pull-in-data-from-a-webhook; batch 1 @ 5s; resume via execution.resumeUrl)
→ Upsert → data table → downstream research/messaging/staging
```

## Engineering rules
1. Map each stage to an explicit n8n node; reference prior nodes by exact name (`$node["Name"].json.…`).
2. Credentials are node credentials (HubSpot OAuth2, Clay API key) — never inline secrets.
3. Add retry (`retryOnFail`, `waitBetweenTries`) on webhook calls to Clay.
4. Keep the "Set Yesterday Range" code node as the single time-source for the intent/ABM window.
5. Add filter fields matching the HubSpot properties the workflow reads
   (`zoominfo___most_recent_workflow_date`, `factors_abm__workflow_date`, `num_associated_deals`, `lifecyclestage`, `type`, `properties.name`).

## Debugging
- Use the n8n Execution Analyst to pull node-level errors and stop-reason per execution.
- Share execution IDs (never raw payloads) with the analyst for diagnosis.
- Patch only the failing node; version the workflow JSON via git.

## Guardrails
- Dry-run by default; never activate production workflow without an approval event.
- Never log secrets or whole payloads containing PII.
- Suppression/do-not-contact enforced before any staging/enrollment node.
