# Security Pillar Deep-Dive — TurnRiverSDR (Amazon Bedrock AgentCore)

This is the detailed security review for the **Security** pillar of the Well-Architected Framework review (see [`WAFR_REVIEW.md`](./WAFR_REVIEW.md)). It covers the AWS-managed infrastructure that the [`cdk/stack.py`](./cdk/stack.py) provisions plus the guardrails that must apply across the whole platform (Supabase, n8n, Vercel, provider integrations).

**Threat model in one sentence:** an attacker — external aggressor or a compromised portfolio-company session — must **never** be able to (a) read another tenant's PII/credentials/pipeline data, (b) cause the agent to send outreach beyond an authenticated, audited approval, (c) escalate to IAM/KMS/S3 broad privileges, or (d) exfiltrate secrets held outside AWS.

---

## 1. Identity & Access Management (least privilege, role separation)

**Principle: implement a strong identity foundation + keep people away from data.**

- **Role separation (no shared credentials):**
  - `turnriver-<env>-agent-runtime` — assumed by `bedrock.amazonaws.com`. Reads S3 skills, writes its own CloudWatch log group, decrypts skills (read-side KMS), invokes the single approved Bedrock model. **Cannot** write S3, touch IAM, or invoke other models.
  - `turnriver-<env>-admin-deploy` — assumed by account/CI principals. Runs `cdk deploy`, `agentcore` CLI, syncs skills. **Cannot** create IAM principals, change bucket policies, or weaken KMS.
- **Permissions boundary** (`turnriver/<env>/boundary`) on both roles: explicit `Deny` of creating users/groups/access keys and of `s3:PutBucketPolicy`/ACL actions — an explicit deny of public access that survives policy changes.
- **Scoping to the minimum ARN:**
  - `s3:Get*` restricted to the skills bucket.
  - `logs:CreateLogStream` / `PutLogEvents` restricted to the one agent log group.
  - `bedrock:InvokeModel` pinned to a single foundation-model ARN.
  - `iam:PassRole` allowed only to the runtime role and only `PassedToService=bedrock.amazonaws.com`.
- **Enforcement at two layers** so a boundary bypass still can't grant ambient broader access.
- **Policy JSON** for all roles is in [`IAM_LEAST_PRIVILEGE.md`](./IAM_LEAST_PRIVILEGE.md).

**Gaps / actions**
- Replace the broad `<account>` assumed-by for the deploy role with a scoped federated/CI principal (`*` → explicit ARN). *To be validated at deploy.*
- Add a Bedrock **resource policy** limiting the model/agent endpoint to the runtime role ARN so inference can't be driven from another identity.
- Human approvers authenticate with MFA; shortest convenient session (≤1 hour).

---

## 2. Encryption (KMS at rest, TLS in transit)

**Principle: protect data in transit and at rest.**

- **At rest:** a single KMS **customer-managed key** (`alias/turnriver/<env>/agent-infra`) with **key rotation enabled** encrypts the skills bucket and the CloudWatch log group. S3 is versioned (`s3:GetObjectVersion` exists) so encrypted old versions remain recoverable under the same key.
- **In transit:** every S3 access is forced to TLS by `enforce_ssl=True` **and** a bucket-policy `Deny` on `aws:SecureTransport=false`; every object must be written with `s3:x-amz-server-side-encryption: aws:kms` or the request is denied.
- **Key management:** admin role's KMS access is conditioned `kms:ViaService = logs.<region>.amazonaws.com`; runtime gets `grants_decrypt` only.

**Gaps / actions**
- Add an explicit KMS **key policy** restricting `kms:Decrypt` to the runtime role and `kms:Encrypt` to the admin role + logs service (the `ViaService` condition currently sits on the IAM side only). *Recommended.*
- Verify Supabase (Postgres at rest / TLS) and Vercel (TLS/edge) encryption settings — they're outside AWS provisioning and must be confirmed. *To be validated at deploy.*
- Never rely on default/identity-managed keys for this workload's data class; keep the CMK.

---

## 3. Data Protection (secrets, env-only refs, sensitivity classes)

**Principle: keep people away from data; protect data in all states.**

- **Secrets policy — no client-side keys:** no real secrets exist in the CDK or any repository file. Values are **ENV-var refs only** (`os.environ.get(...)` in `stack.py` / `app.py`). Placeholders start with `urn:` / template tokens.
- **Required secrets location:** Supabase connection, provider/CRM credentials, n8n webhook keys, and any model API keys must live in **AWS Secrets Manager / SSM Parameter Store** and be injected as environment variables at runtime — never baked into code, skill files, S3 objects, or the Vercel client bundle.
- **Sensitivity classes** (each object, bucket, log group, and role carries the applicable class in its `DataSensitivity` tag):
  | Class | Examples | Key controls |
  |---|---|---|
  | **PII** | Buyer name, work email, signature, contact notes | Least-privilege access, retention limits, RLS, minimal collection |
  | **Health** | (none directly — maintained as a class to prove review) | If introduced: PHI-equivalent handling, HIPAA posture |
  | **Credentials** | Salesforce/CRM creds, provider API tokens | Secrets Manager only, rotate on rotation policy, never logged |
  | **Confidential** | Pipeline revenue, ICP research, deal data | Access scoped per tenant, audited reads, no public exposure |
- **Tenant isolation:** Supabase **Row-Level Security** keyed on `tenant_id` is mandatory; n8n workflows and any S3 prefixes must be tenant-scoped. This is the primary multi-tenant control under review and is *to be validated at deploy*.

**Gaps / actions**
- Centralize secrets; add a rotation schedule for provider/CRM creds.
- Enforce a scan/test rule that **no secret literal** is ever committed (blocklist in CI on `*.env`, `secret`, key patterns).
- Ensure approval-gate data and staged-outreach drafts respect retention/lifecycle rules (tie to RTO/RPO in Reliability).

---

## 4. Logging & Detection (CloudTrail, CloudWatch)

**Principle: enable traceability; prepare for security events.**

- **CloudWatch:** agent runtime logs go to `/aws/turnriver/<env>/agent` (KMS-encrypted, 7-day retention). This is the runtime's traceability surface.
- **Detection gaps:**
  - **CloudTrail is not yet provisioned** — required to audit management events (IAM role changes, KMS key policy changes) and **S3 data events** on the skills bucket (who read what, when). This is the single biggest detection gap.
  - No **Config rules / security hub** baselines; no guardrails on policy drift.
  - No alerting/alarm wiring from CloudWatch (see Operational Excellence).

**Gaps / actions (priority)**
1. Enable **CloudTrail** (management events + S3 data events on the skills bucket) → a **WORM** (object-lock Write-Once-Read-Many) S3 archive for tamper-resistant audit.
2. Add CloudWatch alarms for anomalous patterns: spikes in failed model invocations, unexpected cross-tenant access errors, repeated `AccessDenied` on the skills bucket.
3. Subscribe relevant log streams to a detection pipeline for review; do not store only 7 days for compliance-relevant events (tier to long-term S3 IA).

---

## 5. Governance (approval gates, dry-run, no-scope-expansion)

**Principle: automation that enforces the organization's control boundaries.**

- **The core governance invariant:** *no external sending until human approval.* Enforcement points:
  - n8n stages all outreach and **blocks** the external-send step behind an approval gate.
  - The AgentCore agent is scoped to **produce** ICPs, researched/qualified leads, sequence drafts, and staged outreach — it is given no capability to send.
  - The IAM runtime role has **no** `ses:*`, `pinpoint:*`, `smtp`, or outbound-integration permissions — a technical enforcement of "cannot send," independent of application logic.
- **Dry-run & no-scope-expansion rules:**
  - All agent runs are **dry-run** by default in non-production; a prod run requires explicit, auditable activation.
  - **No-scope-expansion rule:** a skill/config update may never broaden the actions a tenant can cause the agent to take (no new send channels, no new data exfiltration paths). Enforced at review time by a scope-diff checklist on every skill/CDK change.
- **Traceability of sends:** any approved automation must carry an **approval reference** (who/when/which staged draft) propagated onto the outbound record for audit.
- **Policies-as-code:** the boundary + deny statements live in `stack.py`; `cdk-nag` runs during synth to catch regressions (Security/S3/encryption rule packs).

---

## 6. Supply-chain (dependency pinning)

**Principle: only run what you have vetted; control your dependencies.**

- **Code IaC:** `cdk/requirements.txt` pins `aws-cdk-lib>=2.100,<3`, `constructs>=10,<11`, `cdk-nag>=2.28,<3` — semver-pinned with upper bounds; no floating/unpinned installs.
- **Python/runtime deps:** any Lambda-like entrypoints and `agentcore`-dependent tooling must pin exact versions in `requirements.txt`/lockfiles and rebuild reproducibly.
- **n8n nodes/packages:** pin versions; vet custom nodes; avoid community nodes with unfettered HTTP/FS access.
- **Vercel frontend:** pin `package-lock.json`/`pnpm-lock.yaml`; run `npm audit` in CI; verify supplier provenance for build-time deps.
- **Image/OCI artifacts:** use pinned digest references (not `latest`) where containers are involved; prefer AWS-managed runtimes with a supported patch cadence.
- **Model/provider supply chain:** the Bedrock model is pinned to a single ARN/version; any model-version change goes through the same review gate as a skill change.

The three explicit `Deny` layers (block-public-access, boundary deny, require-TLS/KMS) plus the "no-send permission" IAM constraint are the non-negotiable security backbone; the recommendations above close the remaining detection and key-scoping gaps and all are *to be validated at deploy*.
