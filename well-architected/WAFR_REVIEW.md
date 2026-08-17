# AWS Well-Architected Framework Review — TurnRiverSDR

**Subject:** TurnRiverSDR — a governed, multi-tenant AI SDR agent for Turn/River Growth Equity and its portfolio companies (SolarWinds, StarLIMS, ASCI, Commio, Invicti, Paessler, Tufin).
**Lens applied:** Serverless AI-agent workload (Amazon Bedrock AgentCore). **Region:** us-east-1.
**Review date:** 2026-08-13 · **Reviewer:** WAFR subagent · **Status:** Initial review — findings & recommendations, not an approval gate.

**Data sensitivity classification (per WAF security lens):** The workload holds and processes *Credentials* (vendor login/Salesforce creds), *PII* (buyer names, work emails, signatures), *Health* (none directly), and *Confidential business data* (pipeline revenue, ICP research, deal information). Each class drives distinct controls below.

---

## Architecture summary (what we are reviewing)

| Component | Implementation | Notes |
|---|---|---|
| Agent runtime | Amazon Bedrock AgentCore (`agentcore` CLI / CDK) | Multi-agent orchestration, model invocation, tool use |
| Central state | Supabase / PostgreSQL | ICPs, leads, sequences, staged outreach |
| Workflow automation | n8n | Sequence orchestration, staging, notifications |
| Frontend / portal | Vercel | Operator dashboards, approval UI |
| Skill/config store | S3 (`turnriver-<env>-skills`) | Versioned skills, prompts, config snapshots |
| Ops/monitoring | CloudWatch log group | `env_tag`-scoped agent runtime logs |
| Encryption at rest | KMS CMK, key rotation enabled | S3 + logs; (Supabase + Vercel own their at-rest encryption — out of scope for provisioning) |
| Identity | IAM roles + permissions boundary | Runtime role, admin/deploy role, explicit deny of public access |

**No external sending without human approval** is the workload's defining governance control and recurs throughout every pillar below.

---

## Pillar 1 — Operational Excellence

**Design principles applied (need):** *Operations as code*, *make frequent, reversible, small changes*, *refine ops procedures frequently*, *anticipate failure*, *learn from operational failures*.

**Key questions asked**
- How do you understand the health and performance of the agent? (logs, metrics, traces)
- How do you deploy, test, and roll back the agent and its skills?
- How do you handle operator intervention and approvals without blocking the pipeline?
- How are runbooks documented, tested, and stored as code?

**What's implemented**
- CloudWatch log group `/aws/turnriver/<env>/agent` with **7-day retention** and KMS encryption — a real observability surface for the agent runtime.
- Infrastructure fully defined as code (CDK `stack.py`) — reproducible, auditable, `git`-tracked.
- Environment-tagged resources (`dev`/`prod` by `TURNRIVER_ENV`) enabling per-env testing before promotion.
- Approval gates in n8n formalize the human-in-the-loop control.
- Skills stored versioned in S3 — enables rolling back a skill's content version.

**Gaps / risks**
- No structured **metrics/alarms** yet (no dashboards, no CloudWatch alarms on error rates, no SLO definitions).
- No **distributed tracing** (active tracer/X-Ray) across AgentCore → Supabase → n8n hops.
- No documented **runbook** as part of IaC (playbooks for agent drift, failed outreach, model degradation).
- No **chaos / failure injection** for the approval gate or the state DB.
- **Multi-tenancy** creates blast-radius and tenant-isolation questions that are unreviewed (see Security).
- Log retention is single-tier (7 days); no tiering to S3 for audit/forensic purposes.

**Recommendations**
1. Add CloudWatch alarms + a simple dashboard keyed on error rate, invocation latency, and approval-gate throughput. Define SLOs (e.g., p95 agent response, % of staged outreach approved within X).
2. Introduce the X-Ray / active-tracer SDK at the AgentCore entrypoints and n8n webhooks to get end-to-end traces.
3. Commit runbooks alongside CDK (e.g., `runbooks/` written as code, linked from log-group description).
4. Add a per-tenant partitioning scheme in Supabase (tenant_id RLS) and test isolation via automated checklist.
5. Use CloudWatch log subscription/Export to archive logs to a long-term S3 bucket before retention expiry.

---

## Pillar 2 — Security

**Design principles applied (need):** *Implement a strong identity foundation*, *enable traceability*, *apply security at all layers*, *automate security best practices*, *protect data in transit and at rest*, *keep people away from data*, *prepare for security events*.

> Deep-dive in [`SECURITY_PILLAR.md`](./SECURITY_PILLAR.md) and policy JSON in [`IAM_LEAST_PRIVILEGE.md`](./IAM_LEAST_PRIVILEGE.md).

**Key questions asked**
- How is identity scoped and least-privileged?
- How is data protected at rest and in transit, including the sensitivity classes above?
- How are secrets handled (never client-side)?
- What logging/detection/traceability is in place?
- How is the "no external sending without approval" control enforced and audited?

**What's implemented**
- IAM **role separation**: runtime role (`bedrock.amazonaws.com` service principal) vs. admin/deploy role — no shared credentials.
- **Permissions boundary** managed policy denies creating users/groups/access keys and denies making S3 public.
- **Explicit bucket denies** (non-TLS transport, non-KMS SSE) on the skills bucket, plus `BlockPublicAccess.BLOCK_ALL` and `enforce_ssl=True`.
- **Encryption at rest**: KMS CMK (key rotation on) encrypts S3 skills + CloudWatch logs. **In transit**: enforced TLS (`enforce_ssl`, `aws:SecureTransport` deny) on all S3 access.
- Least-privilege runtime: `s3:Get*` on skills only, `logs:*` on the log group only, `bedrock:InvokeModel` on the single model ARN, `kms:Decrypt` (read-side only).
- Bedrock model invocation limited to a single foundation-model ARN (runtime) and `ListFoundationModels` (admin).

**Gaps / risks**
- No **CloudTrail** yet — required for full audit of IAM/S3/bedrock events (see detection below).
- Secrets (Supabase, provider creds) are outside AWS and must be verified to be in **Secrets Manager / Parameter Store** with env-only references (marked *to be validated at deploy*).
- No formal **data sensitivity tagging** on all objects/buckets/log groups beyond a `DataSensitivity: confidential` tag.
- PII/credential handling in Supabase/n8n not yet reviewed for RLS and least-privilege SQL roles.
- No **encryption key policy** restricting who can `kms:Encrypt`/`Decrypt` beyond `ViaService` on the admin role (tighten to explicit principals).
- Bedrock model access is a **single ARN**, but there is no resource policy restricting model endpoint use to the agent runtime only.

**Recommendations**
1. Enable CloudTrail (management + data events on the skills bucket) and route to a locked (Write-Once-Read-Many) S3 bucket.
2. Move all secrets to Secrets Manager / SSM Parameter Store; use env-var refs only; forbid client-side keys; validate at deploy.
3. Tag buckets/log groups/roles with the `DataSensitivity` class that applies (credentials ≈ PII ≈ confidential).
4. Add a KMS key policy limiting `kms:Decrypt` to the runtime role and `kms:Encrypt` to the admin role + logging service.
5. Add a Bedrock resource policy scoping model access to the runtime role ARN.
6. Keep the human-approval gate as the **authoritative release control**; add cryptographic signing/audit of any automated send (a "send" must always carry an approval reference).

---

## Pillar 3 — Reliability

**Design principles applied (need):** *Automatically recover from failure*, *test recovery procedures*, *scale horizontally*, *stop guessing capacity*, *manage change in automation*.

**Key questions asked**
- How is the agent resilient to model/tool/storage failures?
- How is state (Supabase) recovered and backed up?
- Are failure paths (model outage, rate-limit, Supabase down) handled gracefully?
- Is there an availability/durability target and are recovery procedures tested?

**What's implemented**
- Versioned S3 skills bucket — enables recovery of a prior skill/config version.
- KMS key rotation enabled — durable crypto material handling.
- State in a managed Supabase/Postgres (managed durability responsibility largely delegated to provider — good).
- Human-in-the-loop staging means a model failure does not auto-fire outreach — a natural failure containment.

**Gaps / risks**
- No defined **RTO/RPO** for Supabase state; no tested **backup/restore** procedure in IaC/review.
- No **retry/idempotency** strategy documented for AgentCore invocations (rate limits, transient Bedrock/Supabase errors).
- Single-region deployment (us-east-1) — no cross-region DR for state or skills.
- No **alarms on upstream dependencies** (Bedrock availability, Supabase availability).
- No **health-check/LWT** for the agent entrypoints or the approval-gate service.
- n8n as a single orchestrator is a potential single point of failure.

**Recommendations**
1. Define and document RTO/RPO (recommend Supabase PITR + scheduled exports); test restore on a schedule (FTR — failure test routine).
2. Implement idempotent invocation keys and bounded exponential-backoff retry with dead-letter handling for staged outreach.
3. Add health checks/alarms on Bedrock, Supabase, n8n, and the approval gate; alert on SLO breach.
4. Plan cross-region disaster recovery for the skills bucket (S3 CRR) and a documented failover decision tree.
5. Add an automated recovery drill: shut down n8n/Supabase in staging and verify the pipeline degrades safely and does not auto-send.

---

## Pillar 4 — Performance Efficiency

**Design principles applied (need):** *Democratize advanced technologies*, *go global in minutes*, *use serverless architectures*, *experiment more often*, *mechanical sympathy*.

**Key questions asked**
- Are compute (model, DB, orchestration) resources right-sized?
- Is the right model class chosen for the task (ICPs, qualification, drafting)?
- Are data-access patterns and lookup paths efficient?
- Is there capacity headroom without over-provisioning?

**What's implemented**
- **Serverless-by-design** (AgentCore, Lambda-like entrypoints, S3, CloudWatch) — no idle-capacity waste.
- Model invocation on a single, task-appropriate model; frontend served on Vercel edge — latency optimised.
- Skills/config stored in S3 with `enforce_ssl` — quick, cached reads.
- State in managed Postgres — indices/query optimisation largely delegated to provider (ensure proper indexes).

**Gaps / risks**
- No **model cost/quality A/B** framework across candidate models/versions; the pinned model may be over- or under-provisioned for the workload.
- No **performance baselines** or load tests for multi-tenant throughput (concurrent ICP research + lead qualification).
- No **caching layer** for repeated lookups (e.g., identical ICP queries across tenants) — potential redundant model invocations/cost.
- No review of Supabase query patterns / indexes / connection pooling under load.
- No latency SLO monitoring (ties to Pillar 1).

**Recommendations**
1. Build a model benchmark harness (quality vs. latency vs. token cost) for ICP/qualify/draft sub-tasks; re-evaluate quarterly.
2. Load-test multi-tenant contention and set concurrency limits at the AgentCore and n8n layers to prevent thundering-herd invocations.
3. Cache deterministic artifacts (resolved ICP templates, static enrichment results) in a cache (DAX/ElastiCache or Supabase materialised views) to cut repeated model/DB calls.
4. Use CloudWatch metrics on invocation + Postgres slow-query logging to right-size over time.
5. Ensure DB indexes cover the lead/ICP read paths and use connection pooling under concurrency.

---

## Pillar 5 — Cost Optimization

**Design principles applied (need):** *Implement Cloud Financial Management*, *adopt consumption model*, *measure overall efficiency*, *stop spending money on undifferentiated heavy lifting*, *analyze and attribute expenditure*.

**Key questions asked**
- Is the workload paying only for what it uses?
- Are model tokens, S3 reads, and DB ops attributed to tenants/cost centers?
- Are there idle or redundant resources (right-sizing)?
- Is cost monitored and charged-back to portfolio tenants?

**What's implemented**
- **Serverless consumption model** throughout (no permanent compute to pay for at idle).
- `CostCenter: turnriver-gpe` + `Application/Environment` **tags** on all CDK-created resources — a real attribution baseline.
- Managed services (Bedrock, Supabase, Vercel, S3, CloudWatch) — undifferentiated heavy lifting outsourced.

**Gaps / risks**
- **Model token spend** is the dominant, volatile cost driver and is not currently budgeted/alarmed.
- Retained resources (`RemovalPolicy.RETAIN`) can accumulate orphaned KMS keys/buckets/old versions → cost + clutter (deliberate safety trade-off, needs a lifecycle sweep).
- No **budget/alarm** on the account or per-tenant; no tag-based **chargeback report** to portfolio companies.
- Versioned S3 keeps every skill version forever by default — no lifecycle policy to expire old versions.
- No monitoring of CloudWatch data-ingestion / log-ingress cost; no S3 Infrequent Access tier for long-term logs.

**Recommendations**
1. Create AWS Budgets + alerts for total cost and **per-tenant model-token cost**; alert at 75% / predicted 100%.
2. Add an **S3 lifecycle policy** on the skills bucket (e.g., expire old non-current versions after 30 days, transition cold snapshots to S3 IA/Glacier IR).
3. Publish a tag-based chargeback report to portfolio tenants (per `TURNRIVER_ENV`/`CostCenter`).
4. Reduce CloudWatch/PutLogEvents volume via structured, sampled logging; route long-term logs to S3 IA.
5. Run a quarterly **right-sizing** review of model choice, provisioning, and Supabase tier vs. utilisation.

---

## Pillar 6 — Sustainability

**Design principles applied (need):** *Understand impact*, *establish sustainability goals*, *maximize utilization*, *anticipate and adopt new hardware/software offerings*, *use managed services*, *reduce downstream impact*.

**Key questions asked**
- Where does the workload's energy footprint concentrate?
- Are resources maximally utilised (no idle compute, no wasteful data movement)?
- Are managed/efficient services preferred over self-managed equivalents?
- Is compute right-sized to avoid over-provisioning?

**What's implemented**
- **Serverless first** — no permanently-running EC2 footprint; idle resources don't consume energy.
- **Managed services** (Bedrock, S3, CloudWatch, Supabase, Vercel) — AWS/provider power-efficient datacenters, no self-managed servers.
- Single-region, single-account architecture — minimal cross-region data movement / duplication (good, pending DR trade-off at Pillar 3).
- Versioned S3 but with no lifecycle (see below → deduping/expiring tiers is the biggest lever).

**Gaps / risks**
- No **explicit sustainability SLO** or measurement of token/compute per task — the biggest reducible impact is **unnecessary model invocations** (redundant inferencing).
- No **lifecycle policy** means old skill versions persist indefinitely (storage + downstream processing).
- Cross-region DR (recommended at Pillar 3) will add some duplication — implicitly accepted, should be size-justified.
- Frontend on Vercel (managed) is reasonable; any heavy client-side processing should be kept minimal.

**Recommendations**
1. Set a sustainability SLO: track **tokens + invocations per qualified lead/ICP** and drive reductions via the caching + benchmark work in Pillar 4.
2. Add S3 lifecycle policies (expire non-current versions, transition cold data to S3 Glacier Instant/IA) to prevent permanent cold storage.
3. Consolidate and dedupe shared skill/prompt assets across tenants to avoid redundant replicated copies.
4. Prefer right-sizing and efficient model classes (Pillar 4) — efficiency is the most direct carbon lever for AI workloads.
5. Document the energy trade-off of DR replication (Pillar 3) and accept only the minimum required copy.

---

## Consolidated priority recommendations

| # | Finding | Pillar(s) | Effort | Impact |
|---|---|---|---|---|
| 1 | Restrict model invocation role to single model ARN + resource policy | Security | Low | High |
| 2 | Enable CloudTrail + WORM S3 archive | Security/OpsEx | Low | High |
| 3 | Secrets in Secrets Manager/SSM, env-only refs, no client-side keys | Security | Low | High |
| 4 | S3 lifecycle policies on skills bucket (expire versions, tier cold) | Cost/Sustainability | Low | Medium |
| 5 | CloudWatch alarms + dashboard + SLOs | OpsEx/Reliability | Medium | High |
| 6 | AWS Budgets + per-tenant token cost chargeback | Cost/OpsEx | Medium | High |
| 7 | Retry/idempotency + DLQ for staged outreach | Reliability | Medium | High |
| 8 | Baseline model benchmark + caching (tokens = primary cost/carbon lever) | Perf/Cost/Sustain | Med-High | High |
| 9 | Define/test RTO/RPO for Supabase + restore drill | Reliability | Medium | Medium |
| 10 | KMS key policy restricting encrypt/decrypt to explicit principals | Security | Low | Medium |

*Anything marked "to be validated at deploy" in this document or the IaC must be confirmed against the live account before the control is considered satisfied.*
