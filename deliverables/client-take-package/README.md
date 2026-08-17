# TurnRiverSDR — Complete AWS Deliverable Package

Packaged for **Patrick Diamitani** (Solutions Architect) and the **Turn/River** client.
This is the full, working build: a governed, multi-tenant AI SDR agent on **Amazon Bedrock
AgentCore**, hardened to the **AWS Well-Architected Framework**, with a portable migration
package the client can take into their own AWS account if they buy.

## What's here

| Folder | Contents |
|---|---|
| `backend/` | **The working AgentCore backend** — `agentcore.yaml` (project config), `agent.py` (Master Agent harness entrypoint: routes chat through PAL → GTM → RAG-DAL → Qualifier → Sequence → Compliance → Planner), `action_groups.json` (9 function contracts), `requirements.txt`, `README.md`. Verified: runs locally (self-test, mock-model fallback), compliance gate **blocks** side-effects. |
| `souls/` | All 9 agent identity/procedure files (master + 8 children). |
| `skills/` | All 9 reusable `skill.md` procedures (lead-gen, research, copywriting, gtm-architect, clay/amplemarket/n8n-engineer, n8n-execution-analyst, PAL). |
| `well-architected/` | AWS WAFR deliverable: 6-pillar `WAFR_REVIEW.md`, CDK IaC (`cdk/app.py`, `cdk/stack.py` — S3 skills bucket + KMS + least-privilege IAM + CloudWatch + cdk-nag), `IAM_LEAST_PRIVILEGE.md`, `SECURITY_PILLAR.md`. CDK compiles. |
| `case-study/` | The Solutions Architect case study — `CASE_STUDY.md`, `EXEC_SUMMARY.md` (1-pager), `MIGRATION_PACKAGE.md` (5-step migration runbook + no-lock-in guarantees). |

## Verification status (honest)

- **Backend harness: PASSED LIVE against Amazon Bedrock (Aug 13, 2026).** Using the AWS
  Bedrock bearer token + inference profile `us.anthropic.claude-sonnet-4-5-20250929-v1:0`,
  the agent produced real, live model responses:
  - **ICP/research request → `gtm-strategist`, `mode=live`, compliance PASS** (routing:
    `pal-intake → gtm-strategist`).
  - **Enrollment/side-effect request → `compliance-gate` BLOCKS it, `mode=live`,
    `compliance.pass=false`** (routing: `pal-intake → sequence-architect →
    automation-planner → compliance-gate → pending-approval`; nothing sent/enrolled/
    activated). Evidence: `verification/live-bedrock-proof.json`.
- **Local self-test: PASS** (`python agent.py`, no/API-less mock fallback) so the pack runs
  offline too.
- **CDK: PASS (compile)** — `app.py` + `stack.py` compile; `cdk synth`/deploy require a
  credential with S3/CloudFormation/IAM (the Bedrock bearer token grants Bedrock + runtime
  invoke + some control-plane reads, but **S3 is still under the quarantined key**, so a
  full `cdk deploy` / `agentcore deploy` to provision S3-bootstrapped infra needs a
  full-IAM AWS credential).
- **Live invoke: PROVEN.** Bedrock Converse via boto3 returned real model text under the
  bearer token (`BEDROCK_V3_OK`). The harness routes and gates correctly against live AWS.

## Migration (when the client buys)

See `case-study/MIGRATION_PACKAGE.md`. In short: `git clone / unzip` → set env (AWS creds,
model access, tenant keys) → `cd well-architected/cdk && cdk deploy` → run
`pip install -r backend/requirements.txt && python backend/agent.py` → invoke via
`agentcore` / `boto3 bedrock-agentcore-runtime`. No vendor lock-in: standard AgentCore,
portable IaC, open souls/skills, client controls keys.

---
**Patrick Diamitani** · patrick.diamitani@gmail.com · https://github.com/diamitani
