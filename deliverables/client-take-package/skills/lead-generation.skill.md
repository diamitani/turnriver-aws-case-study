# Skill — Lead Generation (Prospect Discovery)
Use when: finding prospects who match an approved ICP for a portfolio company.

## Procedure
1. Read the approved ICP (firmographics, role, pains, triggers, exclusions).
2. Choose the licensed source for the workspace's data provider:
   - **Clay** — enrichment + enrichment-in-workflow webhooks (pull-in-data-from-a-webhook).
   - **Amplemarket** / **ZoomInfo** — account & contact discovery.
3. Run discovery: upload target list (CSV) OR prompt-driven search OR scheduled daily run based on ICP.
4. Cross-reference the CRM (`hs_last_sales_activity_timestamp`, existing deals) to exclude already-active accounts.
5. Emit candidate list with source + confidence.

## Guardrails
- Only licensed providers; no autonomous scraping or LinkedIn automation.
- Never invent contact data; every field labelled source + confidence.
- Missing connector → tag `requires_new_connector`, surface in BUILD_PROMPT, never assume.
