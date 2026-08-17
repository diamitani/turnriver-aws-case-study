# Skill — n8n Execution Analyst
Use when: anyone wants to check, monitor, audit, or investigate n8n executions — "did my workflow run", "why did it fail", "what failed today", "which workflows are stalled".

## Setup (one-time)
1. Get n8n API key: n8n → Settings → n8n API → Create an API key.
2. Set env vars:
   ```bash
   export N8N_API_KEY="eyJ..."        # required for live pulls
   export N8N_BASE_URL="https://atlas-hxm.app.n8n.cloud"   # re-point to Turn/River instance
   export ALERT_WEBHOOK_URL="..."      # optional, off by default
   export ALERT_DRY_RUN="false"        # only when ready to send real alerts
   ```

## Routing
| User says | Do |
|---|---|
| "check/pull/refresh executions" | `python scripts/ingest.py` (`--full` backfill, `--limit N` pilot) |
| "run the daily report" | `python scripts/run_daily.py` (ingest → alert → dashboard) |
| any question about runs/failures/rates | `python scripts/query.py "<question>"`, read the JSON, relay the `answer` |
| "open the dashboard" | `python dashboard/build.py` → present `dashboard/index.html` |
| offline demo | add `--from-fixtures tests/fixtures` to `ingest.py` |

## Guardrails
- **Read-only n8n API.** Only GET. Never DELETE/activate/deactivate.
- **Secrets from env only.** Never print, log, hardcode, or commit `N8N_API_KEY`.
- **No fabrication.** Absent fields are null; if the store has no data for a question, say so.
- **Alerts dry-run by default** — confirm before setting `ALERT_DRY_RUN=false`.
- **Idempotent.** Re-running ingestion never duplicates executions (upsert on execution ID).
