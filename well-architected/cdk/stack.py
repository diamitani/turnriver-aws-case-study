"""
TurnRiverSDR - Well-Architected supporting infrastructure (CDK stack).

Provisions the governed, multi-tenant AI SDR (TurnRiverSDR) agent's
non-application infrastructure on AWS in us-east-1:

  * S3 skills bucket           -> versioned, KMS-encrypted, AgentCore-runtime read access
  * KMS symmetric key          -> used to encrypt the skills bucket + CloudWatch logs
  * CloudWatch log group       -> runtime / agent execution logs, with retention
  * IAM roles (least privilege)
      - turnriver-agent-runtime   -> read S3 skills, write CloudWatch logs, Bedrock invoke
      - turnriver-admin-deploy    -> CDK deploy + agentcore CLI actions
      - permissions boundary      -> denies public / overly-broad exposure

The stack is scoped so that *no* principal gets broader access than it needs,
and everything uses ENV refs for any configurable/secret values. Nothing here
is a real secret -- only placeholders that must be validated at deploy time
(annotated "to be validated at deploy").

Runtime: run `cdk deploy` from the cdk/ directory.
"""

import os

from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    aws_kms as kms,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct


class TurnRiverWellArchitectedStack(Stack):
    """Well-Architected supporting infrastructure for the TurnRiverSDR agent."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # Parameters / env-driven configuration (ENV refs only, no secrets)
        # ------------------------------------------------------------------
        account = os.environ.get("AWS_ACCOUNT_ID", self.account)
        env_tag = os.environ.get("TURNRIVER_ENV", "dev")

        # Bedrock model id used to invoke the agent runtime. To be validated at deploy.
        model_id = os.environ.get("TURNRIVER_MODEL_ID", "amazon.nova-pro-v1:0")

        common_tags = {
            "Application": "TurnRiverSDR",
            "Environment": env_tag,
            "CostCenter": "turnriver-gpe",
            "ManagedBy": "cdk",
            "Purpose": "well-architected-agent-infra",
            "DataSensitivity": "confidential",
        }
        for k, v in common_tags.items():
            self.tags.set_tag(k, v)

        # ------------------------------------------------------------------
        # KMS key (single CMK used for S3 skills + CloudWatch logs)
        # ------------------------------------------------------------------
        encryption_key = kms.Key(
            self,
            "TurnRiverKmsKey",
            description="KMS key for TurnRiverSDR agent infrastructure (S3 skills + logs)",
            alias=f"alias/turnriver/{env_tag}/agent-infra",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------
        # CloudWatch log group for agent runtime execution & agentcore logs
        # ------------------------------------------------------------------
        agent_log_group = logs.LogGroup(
            self,
            "TurnRiverAgentLogGroup",
            log_group_name=f"/aws/turnriver/{env_tag}/agent",
            retention=logs.RetentionDays.SEVEN_DAYS,
            encryption_key=encryption_key,
        )

        # ------------------------------------------------------------------
        # S3 skills bucket (stores skills / prompts / config snapshots)
        # ------------------------------------------------------------------
        skills_bucket = s3.Bucket(
            self,
            "TurnRiverSkillsBucket",
            bucket_name=os.environ.get(
                "TURNRIVER_SKILLS_BUCKET", f"turnriver-{env_tag}-skills"
            ),
            versioned=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=encryption_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Bucket policy: explicit denies of public / insecure access on top of
        # BlockPublicAccess.BLOCK_ALL (belt & suspenders).
        skills_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                actions=["s3:*"],
                resources=[skills_bucket.bucket_arn, skills_bucket.arn_for_objects("*")],
                principals=[iam.AnyPrincipal()],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )
        skills_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                actions=["s3:*"],
                resources=[skills_bucket.bucket_arn, skills_bucket.arn_for_objects("*")],
                principals=[iam.AnyPrincipal()],
                conditions={
                    "StringNotEquals": {"s3:x-amz-server-side-encryption": "aws:kms"}
                },
            )
        )

        # ------------------------------------------------------------------
        # Permissions boundary policy (applies to all agent IAM roles)
        # ------------------------------------------------------------------
        boundary_policy = iam.ManagedPolicy(
            self,
            "TurnRiverPermissionsBoundary",
            managed_policy_name=f"turnriver/{env_tag}/boundary",
            statements=[
                # Deny creating broad-scope IAM principals / keys from within roles.
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=[
                        "iam:CreateUser",
                        "iam:CreateGroup",
                        "iam:PutGroupPolicy",
                        "iam:PutUserPolicy",
                        "iam:AddUserToGroup",
                        "iam:AttachUserPolicy",
                        "iam:AttachGroupPolicy",
                        "iam:CreateAccessKey",
                    ],
                    resources=["*"],
                ),
                # Deny making buckets/objects public.
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=[
                        "s3:PutBucketPublicAccessBlock",
                        "s3:PutBucketPolicy",
                        "s3:DeleteBucketPolicy",
                        "s3:PutBucketAcl",
                        "s3:PutObjectAcl",
                    ],
                    resources=["*"],
                ),
            ],
        )

        # ------------------------------------------------------------------
        # IAM role: agent runtime (reads S3 skills, writes logs, invokes Bedrock)
        # ------------------------------------------------------------------
        agent_runtime_role = iam.Role(
            self,
            "TurnRiverAgentRuntimeRole",
            role_name=f"turnriver-{env_tag}-agent-runtime",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            permissions_boundary=boundary_policy,
        )

        # S3: read-only on the skills bucket.
        agent_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                resources=[skills_bucket.bucket_arn, skills_bucket.arn_for_objects("*")],
            )
        )

        # CloudWatch logs: write + list on the agent log group.
        agent_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                resources=[agent_log_group.log_group_arn, f"{agent_log_group.log_group_arn}:*"],
            )
        )

        # KMS: allow the runtime to decrypt skills objects (read-side only).
        encryption_key.grant_decrypt(agent_runtime_role)

        # Bedrock: invoke the model (AgentCore runtime backend). Resource is
        # "*" here but the model id is fixed via resource policy at deploy-time
        # (to be validated at deploy).
        agent_runtime_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[f"arn:aws:bedrock:{self.region}:{account}:foundation-model/{model_id}"],
            )
        )

        # ------------------------------------------------------------------
        # IAM role: admin / deploy (cdk deploy + agentcore CLI). Assumed by a
        # user or CI OIDC role in the account (to be validated at deploy).
        # ------------------------------------------------------------------
        admin_deploy_role = iam.Role(
            self,
            "TurnRiverAdminDeployRole",
            role_name=f"turnriver-{env_tag}-admin-deploy",
            assumed_by=iam.AccountPrincipal(account),
            permissions_boundary=boundary_policy,
        )

        # Read/write the skills bucket (agentcore skill sync, S3 uploads).
        admin_deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                resources=[skills_bucket.bucket_arn, skills_bucket.arn_for_objects("*")],
            )
        )
        admin_deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:PutMetricData",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                ],
                resources=["*"],
            )
        )
        admin_deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:ListFoundationModels"],
                resources=["*"],
            )
        )
        admin_deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[agent_runtime_role.role_arn],
                conditions={"StringEquals": {"iam:PassedToService": "bedrock.amazonaws.com"}},
            )
        )
        admin_deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
                resources=["*"],
                conditions={"StringEquals": {"kms:ViaService": f"logs.{self.region}.amazonaws.com"}},
            )
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        from aws_cdk import CfnOutput

        CfnOutput(self, "SkillsBucketName", value=skills_bucket.bucket_name)
        CfnOutput(self, "AgentRuntimeRoleArn", value=agent_runtime_role.role_arn)
        CfnOutput(self, "AdminDeployRoleArn", value=admin_deploy_role.role_arn)
        CfnOutput(self, "LogGroupName", value=agent_log_group.log_group_name)
        CfnOutput(self, "KmsKeyArn", value=encryption_key.key_arn)
        CfnOutput(self, "ModelId", value=model_id)
