# Migration & Delivery Package — Turn/River AI SDR Agent

This document describes exactly what the client receives, the prerequisites, the 5-step migration runbook, and the no-lock-in guarantees.

---

## 1. What You Receive (the Client-Take Package)

A complete, self-contained backend project — the **full master build** — ready to run in the client's own AWS account:

```
turnriver-sdr/
├── agentcore.yaml          # AgentCore config: master + 8 role agents (TurnRiverSDR)
├── agent.py                # Python runtime entrypoint for the orchestrator
├── action_groups.json      # Machine-readable action contracts per agent role
├── skills/                 # 9 markdown skill procedures
│   ├── lead-gen.md
│   ├── research.md
│   ├── copywriting.md
│   ├── gtm-architect.md
│   ├── clay-engineer.md
│   ├── amplemarket-engineer.md
│   ├── n8n-engineer.md
│   ├── n8n-execution-analyst.md
│   └── pal.md
├── souls/                  # Identity/procedure docs per agent
├── infra/                  # CDK infrastructure-as-code (with cdk-nag)
│   ├── stack.ts / app.py   # S3 skills bucket, KMS, IAM, CloudWatch
│   └── cdk.json
├── env.example             # Environment template (secrets are NEVER committed)
├── README.md               # Build + run + migrate instructions
└── runbook/                # This migration runbook, as a checklist
```

Supporting configuration for the surrounding stack (Supabase schema, n8n workflows, Vercel env, Composio tool whitelist) is documented in the package so the client can reproduce the full environment.

---

## 2. Prerequisites

Before migration, the client's account must have:

1. **A healthy AWS credential** — an IAM principal with permission to run `cdk deploy` in `us-east-1`, scoped to the resources the stack defines (Bedrock AgentCore, S3, KMS, IAM, CloudWatch). The stack itself applies **least-privilege** via cdk-nag.
2. **Bedrock model access enabled** in `us-east-1` for the model tenants used by the AgentCore runtime.
3. **The surrounding SaaS tenants configured** — Supabase instance/creds, an n8n instance, a Composio API key, and the service keys for Clay and Amplemarket. These are supplied as environment variables at deploy/runtime (ENV-only; never in the repo).
4. **Python 3.11+** and the CDK CLI locally, or a CI pipeline with the same.

---

## 3. The 5-Step Migration Runbook

Migration is a deterministic CDK deploy — no rebuild, no re-architecting. Steps:

### Step 1 — Clone / Package
```
git clone <client-take-package> turnriver-sdr
cd turnriver-sdr
```
Confirm the package hash matches the delivered manifest (integrity check).

### Step 2 — Set Environment
- Copy `env.example` to `.env` and fill in secrets: Supabase creds, n8n URL/token, Composio key, Clay & Amplemarket keys, Bedrock model IDs.
- **Secrets only go into the environment** — never into any committed file, artifact, or image.

### Step 3 — Deploy the Infrastructure (CDK)
```
cd infra
cdk synth      # validates the stack (cdk-nag runs guardrails)
cdk deploy     # provisions AgentCore configs, S3 skills bucket (KMS),
               # least-privilege IAM, CloudWatch — deterministically
```
Deployment is idempotent and reproducible from source.

### Step 4 — Invoke the AgentCore Agent
```
agentcore invoke --agent TurnRiverSDR --input <test-intake>
```
Run the smoke tests included in the package (a synthetic intake → strategy → research → qualification → sequence → **stop at approval**) to confirm the full pipeline functions in the new account.

### Step 5 — Verify Governance & Audit
- Confirm a dry-run enrollment **blocks** without an approval event.
- Confirm emails/CRM-writes **do not fire** unless approved.
- Confirm suppression/do-not-contact is enforced before staging.
- Confirm `CloudWatch` logs and Postgres audit trail capture source, timestamp, and confidence labels.

**Acceptance criteria:** all smoke tests pass, governance gates hold, and telemetry is visible — at which point the system is live in the client's account.

---

## 4. No-Lock-In Guarantees

Turn/River owns everything and is never bound to a single vendor:

- **Open skills & souls.** The 9 skills and agent souls are plain markdown. The client can read, edit, and version them — teaching the agents is in their control, and any engineer can modify the behavior.
- **Standard Bedrock AgentCore.** The orchestration runs on unmodified Amazon Bedrock AgentCore — a native, widely available AWS service, not a proprietary abstraction. Model choice and configuration stay with the client.
- **Portable Infrastructure-as-Code.** The entire environment is CDK with cdk-nag. Moving it or reproducing it is a deploy, not a rebuild.
- **Client-controlled keys.** Credentials live in the client's environment and never in the package. At any point, the client can rotate or revoke access and the system behaves accordingly.
- **Workspaces & re-skinning.** Each portfolio company is an isolated workspace; adding a new one is configuration, not custom development.

If Turn/River buys, they get a **complete, running, governed AI SDR backend in their own account** — plus the standing ability to evolve it without paying for a rebuild.
