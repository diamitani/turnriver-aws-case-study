"""
TurnRiverSDR - CDK app entrypoint.

Instantiates the Well-Architected supporting infrastructure stack. The
account ID comes from the AWS_ACCOUNT_ID env var (default '148761663702')
and the region is us-east-1 (or AWS_REGION / default).

Run:
    pip install -r requirements.txt
    cdk bootstrap     # once, if not already done
    cdk deploy TurnRiverWellArchitectedStack
"""

import os

import aws_cdk as cdk

from stack import TurnRiverWellArchitectedStack

# Environment for the stack.
env = cdk.Environment(
    account=os.environ.get("AWS_ACCOUNT_ID", "148761663702"),
    region=os.environ.get("AWS_REGION", "us-east-1"),
)

app = cdk.App()

TurnRiverWellArchitectedStack(
    app,
    "TurnRiverWellArchitectedStack",
    env=env,
    description="Well-Architected supporting infrastructure for the TurnRiverSDR AI SDR agent",
)

app.synth()
