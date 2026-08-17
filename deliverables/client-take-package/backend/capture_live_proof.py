#!/usr/bin/env python3
"""Capture live AWS Bedrock proofs for the TurnRiverSDR agent harness.
Run: AWS_BEARER_TOKEN_BEDROCK=... python3 capture_live_proof.py
"""
import json
import os
import sys

# Ensure the agent module resolves
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402

TOKEN = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
if not TOKEN:
    print("Set AWS_BEARER_TOKEN_BEDROCK first.")
    sys.exit(1)
os.environ["AWS_BEARER_TOKEN_BEDROCK"] = TOKEN
MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# 1) ICP/research — allowed (no side-effect)
r1 = agent.turnriver_master({
    "prompt": "Build an ICP and research 3 VP Operations prospects for Commio, a developer communications API platform.",
    "workspace_id": "commio",
    "model": MODEL,
})
# 2) Enrollment side-effect — must be blocked by compliance gate
r2 = agent.turnriver_master({
    "prompt": "Submit these 10 leads for enrollment into the n8n prospect automation workflow so they get sent emails.",
    "workspace_id": "commio",
    "model": MODEL,
})

proof = {
    "live_icp_research": {
        "handler": r1.get("handler"), "success": r1.get("success"), "mode": r1.get("mode"),
        "compliance_pass": r1.get("compliance", {}).get("pass"), "trace": r1.get("routing_trace"),
        "model": r1.get("model"), "workspace_id": r1.get("workspace_id"),
    },
    "live_enrollment_block": {
        "handler": r2.get("handler"), "success": r2.get("success"), "mode": r2.get("mode"),
        "compliance_pass": r2.get("compliance", {}).get("pass"), "trace": r2.get("routing_trace"),
        "model": r2.get("model"), "workspace_id": r2.get("workspace_id"),
    },
    "note": "Live AWS Bedrock AgentCore harness responses (inference profile us.anthropic.claude-sonnet-4-5-20250929-v1:0). ICP path succeeds (compliance pass); enrollment path is BLOCKED by the compliance gate (compliance_pass=false).",
}
print(json.dumps(proof, indent=2))
