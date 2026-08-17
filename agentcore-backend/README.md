# TurnRiverSDR Master Agent — Amazon Bedrock AgentCore Backend

Governed AI-SDR orchestration backend for Turn/River Growth Equity, deployed on
**Amazon Bedrock AgentCore** (`agentcore` CLI v0.26.0, framework
`amazon-bedrock-agentcore`).

The agent logic lives in embedded `soul.md`/`skill.md` content (bundled verbatim
from the turnriver-sdr-agent client package) and is invoked through the
`agent.py` entrypoint harness. This is the **master** agent; the 8 child agency
roles (PAL Intake, GTM Strategist, RAG-DAL Researcher, Prospect Qualifier,
Sequence Architect, Compliance Gate, Automation Planner, NPAO Orchestrator) are
all routed from it with a single governing system prompt.

---

## What this backend does

Implements the master runtime flow, orchestrated only by NPAO Orchestrator:

```
chat intake → PAL intent spec → GTM Strategist → RAG-DAL research
↔ Prospect Qualifier → Sequence Architect → Compliance Gate → approval request
→ Automation Planner dry-run → staged enrollment → results ingestion → dashboard
```

Every response is bounded by the **5 hard governance rules**:

1. No send / enroll / CRM-write / workflow activation without a specific approval event.
2. **ENV:**-only secrets — never embed keys; redact pasted secrets.
3. Never present inferred data as fact — label source, timestamp, confidence.
4. Suppression / do-not-contact before any staging action; suppression always wins.
5. Dry-run preview + re-approval on any scope / count / destination / sequence change.

Memory is **workspace-scoped** (`workspaces/{org}/{workspace_id}/{session_id}`) for
multi-tenant isolation across portfolio companies.

---

## Files

| File | Purpose |
|------|---------|
| `agentcore.yaml` | AgentCore agent definition (entrypoint, runtime, memory, region, tags). |
| `agent.py` | Entrypoint harness — routing, governance gate, memory, provider calls, self-test. |
| `action_groups.json` | Function / action-group contracts for Bedrock action-group wiring. |
| `requirements.txt` | Python deps. |
| `README.md` | This file. |

---

## Local self-test (no network, no API key)

```bash
cd /Users/patmini/Projects/turnriver-aws-case-study/agentcore-backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent.py
```

With no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` set, the harness takes a
**deterministic mock path** and prints a JSON result for each sample request —
proving the pipeline (PAL intake → routing → compliance gate → memory → output)
runs end-to-end without any external call. With an API key it calls the live
provider over `httpx` and returns a real LLM reply.

Output shape per request:

```json
{
  "success": true,
  "handler": "sequence-architect",
  "intent": "sequence",
  "message": "...",
  "routing_trace": ["pal-intake", "sequence-architect"],
  "compliance": { "pass": true, "note": "..." },
  "workspace_id": "demo",
  "model": "claude-sonnet-4-5-20250929",
  "provider": "anthropic",
  "governance": { "boundaries": ["..."] },
  "mode": "mock" | "live"
}
```

---

## Deploy to Amazon Bedrock AgentCore

> **Prerequisite (honest note):** deploying requires a **healthy, non-quarantined
> AWS credential** for `us-east-1` (the `agentcore` CLI / boto3 control plane, and
> the `bedrock-agentcore-runtime` invoke path, both fail against a quarantined,
> inactive, or missing key). Confirm with `aws sts get-caller-identity`.

```bash
# 1. install the CLI + SDK
pip install amazon-bedrock-agentcore==0.26.0

# 2. create the agent from agentcore.yaml (control plane, boto3)
agentcore create                 # registers turnriver-master in us-east-1

# 3. deploy (CDK)
agentcore deploy

# 4. check status
agentcore status
```

### Invoke after deploy

```bash
agentcore invoke --payload '{"prompt": "Create an ICP for Commio",
  "provider": "anthropic", "api_key": "sk-ant-...", "workspace_id": "commio"}'
```

Or via boto3:

```python
import boto3, json
c = boto3.client("bedrock-agentcore-runtime", region_name="us-east-1")
resp = c.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:...",
    payload=json.dumps({"prompt": "...", "workspace_id": "demo"}))
text = "".join(evt["contentBlockDelta"]["delta"]["text"]
               for evt in resp["events"] if "contentBlockDelta" in evt)
```

For a real model in AgentCore, prefer the **Bedrock** provider with a **server-side
model key** (see `manifest.json` tool-permission matrix — "model execution": service
auth, `ENV:AWS_* / BEDROCK_*`, client-side key always denied by default).

### Wiring action groups

Use the contracts in `action_groups.json` to register each function set as a
Bedrock action group bound to the matching `functions/*` handler. Side-effect
groups (`automation_planner_actions`: `stage_enrollment`, `trigger_n8n_dry_run`)
MUST remain behind the compliance gate + human approval. **Important:** a bare
agent update that omits tools/skills **wipes** them — always re-specify on update.

### Env references

All secrets are supplied at runtime via environment/service-config, never
embedded: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `BEDROCK_*`, `CLAY_API_KEY`,
`AMPLEMARKET_API_KEY`, `ZOOMINFO_API_KEY`, `HUBSPOT_OAUTH`, `N8N_BASE_URL`,
`N8N_API_KEY`.

---

## Migration

Per `infra/agentcore.md`, this backend is portable: keep the same `soul.md` /
`skill.md` / `functions/*` content, point Vercel SDK / serverless `fetch`
handlers at the same functions via a thin adapter, and swap the AgentCore
transport — **zero rework of agent logic**, because the logic lives in the
bundled souls/skills, not in the runtime transport.

- Model provider is swappable via the `provider` field (`anthropic` | `openai` | Bedrock).
- Memory strategy is `episodic`; retargetable to another store by implementing
  the same `get_memory_client()` interface.

---

## Security notes

- No secrets in this repo — only `ENV:VAR` references.
- No credentials are ever persisted to memory, chat logs, artifacts, or source.
- Cross-workspace memory/data access is denied by default.
