# IAM Least-Privilege Policy Statements — TurnRiverSDR

This document specifies the exact IAM policy statements backing the Well-Architected infrastructure in [`cdk/stack.py`](./cdk/stack.py). Every statement is scoped to the **minimum resource** the role needs. No real secrets appear anywhere — identifiers are template/placeholder values prefixed with `urn:`, and actual ARNs are *to be validated at deploy*.

Placeholder key (all from the CDK stack env config):

| Placeholder | Meaning | Default |
|---|---|---|
| `<account>` | AWS account id | `148761663702` |
| `<region>` | Region | `us-east-1` |
| `<env>` | Environment tag | `dev` / `prod` |
| `<bucket>` | Skills bucket | `turnriver-<env>-skills` |
| `<model-id>` | Bedrock model | `amazon.nova-pro-v1:0` |
| `<log-group>` | CloudWatch log group | `arn:aws:logs:<region>:<account>:log-group:/aws/turnriver/<env>/agent:*` |

---

## 1. Agent runtime role

**Role ARN:** `arn:aws:iam::<account>:role/turnriver-<env>-agent-runtime`
**Assumed by:** `bedrock.amazonaws.com` (service principal)
**Permissions boundary:** `turnriver/<env>/boundary` (see §4)

Purpose: run the AgentCore agent — read its skills from S3, write execution logs, and invoke the single approved Bedrock model. Nothing else.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ReadSkillsBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/*"
      ]
    },
    {
      "Sid": "CloudWatchWriteAgentLogs",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
      "Resource": [
        "arn:aws:logs:<region>:<account>:log-group:/aws/turnriver/<env>/agent",
        "arn:aws:logs:<region>:<account>:log-group:/aws/turnriver/<env>/agent:*"
      ]
    },
    {
      "Sid": "KmsDecryptSkills",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": ["arn:aws:kms:<region>:<account>:key/<key-id>"]
    },
    {
      "Sid": "InvokeApprovedModel",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": ["arn:aws:bedrock:<region>:<account>:foundation-model/<model-id>"]
    }
  ]
}
```

**Notes / rationale**
- `s3:Get*` only on the skills bucket — the runtime can **never write** S3.
- Logs scope is the single agent log group; the runtime cannot touch other log groups.
- `kms:Decrypt` (read-side) only — no `kms:Encrypt`, so it cannot forge ciphertext.
- Model invoke is pin-scoped to the single model ARN; combined with a Bedrock **resource policy** limiting the endpoint to this role ARN (recommended, see Security gap) it fully constrains inferencing.

---

## 2. Admin / deploy role

**Role ARN:** `arn:aws:iam::<account>:role/turnriver-<env>-admin-deploy`
**Assumed by:** `<account>` principals (human user or CI OIDC role — *to be validated at deploy*)
**Permissions boundary:** `turnriver/<env>/boundary` (see §4)

Purpose: run `cdk deploy`, drive the `agentcore` CLI, sync skills to the bucket, inspect logs, pass the runtime role to Bedrock. Explicitly **not** permitted to touch IAM, KMS, or S3 policies in a destructive way.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3SyncSkillsBucket",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket", "s3:GetObject", "s3:GetObjectVersion",
        "s3:PutObject", "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/*"
      ]
    },
    {
      "Sid": "ObserveLogs",
      "Effect": "Allow",
      "Action": ["logs:DescribeLogGroups", "logs:DescribeLogStreams", "cloudwatch:PutMetricData"],
      "Resource": ["*"]
    },
    {
      "Sid": "ListModels",
      "Effect": "Allow",
      "Action": ["bedrock:ListFoundationModels"],
      "Resource": ["*"]
    },
    {
      "Sid": "PassRuntimeRoleToBedrock",
      "Effect": "Allow",
      "Action": ["iam:PassRole"],
      "Resource": ["arn:aws:iam::<account>:role/turnriver-<env>-agent-runtime"],
      "Condition": { "StringEquals": { "iam:PassedToService": "bedrock.amazonaws.com" } }
    },
    {
      "Sid": "KmsViaLogsService",
      "Effect": "Allow",
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": ["*"],
      "Condition": { "StringEquals": { "kms:ViaService": "logs.<region>.amazonaws.com" } }
    }
  ]
}
```

**Notes / rationale**
- No `iam:*` mutating actions — admin can `PassRole` only to Bedrock and only to the one runtime role.
- No `s3:PutBucketPolicy` / `PutBucketAcl` / `PutObjectAcl` — cannot unintentionally make things public (also blocked by the boundary).
- No `kms:*KeyPolicy`/`kms:PutKeyPolicy` — cannot weaken the key.
- Admin does **not** get `bedrock:InvokeModel` on an ad hoc basis in this minimal statement (only `bedrock:ListFoundationModels`); production model invocation is the runtime role's job. If an admin needs ad hoc inference for testing, add a scoped, *explicitly documented* exception rather than widening this policy.

> *To be validated at deploy:* the actual human/CI principal ARN(s) must replace the broad `<account>` assumed-by in production (prefer a scoped OIDC federated role with 1-hour max-session and MFA for humans).

---

## 3. Skills bucket resource policy

The S3 bucket itself carries **deny-by-default** public-access statements (on top of `BlockPublicAccess.BLOCK_ALL` in the CDK):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyNonTlsAccess",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/*"
      ],
      "Condition": { "Bool": { "aws:SecureTransport": "false" } }
    },
    {
      "Sid": "DenyNonKmsEncryption",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::<bucket>",
        "arn:aws:s3:::<bucket>/*"
      ],
      "Condition": { "StringNotEquals": { "s3:x-amz-server-side-encryption": "aws:kms" } }
    }
  ]
}
```

These mirror the two `Deny` statements in `stack.py` and make the bucket **require TLS and KMS-SSE** for every request, even misconfigured ones.

---

## 4. Permissions boundary (`turnriver/<env>/boundary`)

Attached to **both** roles so any future policy escalation still cannot leak access or create permanent principals:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyCreateBroadPrincipals",
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser",
        "iam:CreateGroup",
        "iam:PutGroupPolicy",
        "iam:PutUserPolicy",
        "iam:AddUserToGroup",
        "iam:AttachUserPolicy",
        "iam:AttachGroupPolicy",
        "iam:CreateAccessKey"
      ],
      "Resource": ["*"]
    },
    {
      "Sid": "DenyMakeS3Public",
      "Effect": "Deny",
      "Action": [
        "s3:PutBucketPublicAccessBlock",
        "s3:PutBucketPolicy",
        "s3:DeleteBucketPolicy",
        "s3:PutBucketAcl",
        "s3:PutObjectAcl"
      ],
      "Resource": ["*"]
    }
  ]
}
```

**Deny checks (the "explicit deny of public access" requirement):**
1. `BlockPublicAccess.BLOCK_ALL` on the bucket (CDK).
2. Bucket resource policy `Deny` of non-TLS and non-KMS requests (CDK, §3 above).
3. Permissions boundary `Deny` of `s3:PutBucketPolicy` / `PutBucketAcl` / `PutObjectAcl` (CDK, §4 above) — even a compromised role cannot re-open the bucket.

---

### Validation notes for deploy
- Apply `cdk-nag` rules (AwsSolutions-IAM4/IAM5 for wildcards, S3/encryption rules) during `cdk synth` to catch regressions.
- After deploy, run `aws iam get-policy-version`/`aws s3api get-bucket-policy` to confirm the statements above are what's live.
- Confirm the `bedrock` service principal is correct for the tuned AgentCore runtime at your account (region/model availability) — *to be validated at deploy*.
