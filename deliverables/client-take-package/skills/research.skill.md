# Skill — Research (Prospect & Company Dossier)
Use when: turning a lead into an evidence-grounded research dossier.

## Procedure
For each account/contact, generate:
1. **Pain-point hypothesis** — from ICP pains + sources (technographics, intent signals, firmographics). Label as hypothesis + confidence.
2. **Company summary** — segment, size, region, industry, tech signals, ICP fit.
3. **Prospect summary** — role title, function, likely pains, trigger personalization hooks.

## Output / schema
```json
{
  "entity": "account|contact",
  "content": "...",
  "citations": [{"url":"","title":"","published_date":"","tier":1|2|3,"credibility":0.0}],
  "confidence": 0.0,
  "source": "..."
}
```

## Guardrails
- Tier-1/2 sources for material claims; mark uncertain if confidence < 0.7.
- Never present inferred data as fact — label confidence per claim.
- Confidential/regulated source files require approval before ingestion.
