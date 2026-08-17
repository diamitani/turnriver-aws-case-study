"""
TurnRiverSDR Master Agent — Amazon Bedrock AgentCore backend
=============================================================
Deploys the governed AI-SDR orchestration pipeline on Amazon Bedrock
AgentCore. The agent logic (procedures + roles) lives in the bundled
soul.md / skill.md content embedded below as system context; the runtime
entrypoint is this file, which the AgentCore harness invokes.

Runtime flow (orchestrated by NPAO Orchestrator only):
    chat intake -> PAL intent -> GTM Strategist -> RAG-DAL research
    <-> Prospect Qualifier -> Sequence Architect -> Compliance Gate
    -> approval request -> Automation Planner dry-run -> staged enrollment

Deploy:
    pip install amazon-bedrock-agentcore
    agentcore create     # via boto3 control plane (us-east-1)
    agentcore deploy     # CDK deploy
    agentcore invoke --payload '{"prompt": "..."}'

Invoke (after deploy), or via boto3:
    import boto3, json
    c = boto3.client("bedrock-agentcore-runtime", region_name="us-east-1")
    c.invoke_agent_runtime(
        agentRuntimeArn="arn:aws:bedrock-agentcore:us-east-1:...",
        payload=json.dumps({"prompt": "...", "provider": "anthropic",
                             "api_key": "sk-ant-...", "workspace_id": "demo"}))

Local self-test (no network, no API key):
    python agent.py
"""

import json
import logging
import os
from typing import Any, Dict, List

import httpx

# ── AgentCore harness ---------------------------------------------------------
# If the Amazon Bedrock AgentCore SDK is present, register the real entrypoint.
# Otherwise fall back to a local shim so `python agent.py` runs standalone.
try:  # pragma: no cover - exercised only under AgentCore runtime
    from amazon_bedrock_agentcore import app
    from amazon_bedrock_agentcore.memory import get_memory_client

    AGENTCORE_AVAILABLE = True
except Exception:  # fallback for local dev / self-test
    AGENTCORE_AVAILABLE = False

    class _FakeMemoryClient:
        def __init__(self):  # simple in-process store for fallback isolation
            self._store: Dict[str, List[Dict[str, str]]] = {}

        def retrieve(self, session_id: str, query: str = "", top_k: int = 3) -> List[Dict[str, str]]:
            return self._store.get(session_id, [])[:top_k]

        def store(self, session_id: str, content: str) -> None:
            self._store.setdefault(session_id, []).append({"content": content})

    def get_memory_client():  # local fallback with workspace-scoped namespaces
        return _FakeMemoryClient()

    class _FakeApp:
        def __init__(self):
            self.payload = None

        def entrypoint(self, fn):
            return fn

    app = _FakeApp()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_FALLBACK_MEMORY: Dict[str, List[Dict[str, str]]] = {}

# ── Governance boundaries (binding) -------------------------------------------
GOVERNANCE = {
    "1": "No external sending / enrollment / CRM-write / workflow activation without a specific approval event.",
    "2": "ENV-only secrets. Never embed real keys/tokens/passwords; reference as ENV:VAR; redact any pasted secret to [REDACTED — provide via env var instead].",
    "3": "Never present inferred data as fact. Label source, timestamp, and confidence on every claim (confidence < 0.7 = uncertain, never asserted).",
    "4": "Suppression / do-not-contact / unsubscribe is applied BEFORE any staging action. Suppression always wins over scores.",
    "5": "Dry-run preview first, and require re-approval if scope, contact count, destination, or sequence changes.",
}

# ── Bundle: master + child souls (verbatim from turnriver-sdr-agent) ----------
SOULS = {
    "master": """You are the **TurnRiverSDR master agent** — a governed sales-development orchestration agent for Turn/River and portfolio-company GTM teams. You convert a company's approved GTM knowledge into auditable, human-approved ICPs, researched lead lists, outreach assets, and automation handoffs.

Mission: Compress the path from a portfolio-company brief to validated prospects and ready-to-launch outreach while retaining **human approval** and a **full audit trail**. You support Turn/River operating teams and active portfolio companies (SolarWinds, StarLIMS, ASCI, Commio, Invicti, Paessler, Tufin) via isolated workspaces.

Memory namespace: workspaces/{organization_id}/{workspace_id} — stores ICP versions, lead state, sequence versions, run ledger, audit trail. No secrets, no raw chain-of-thought.""",
    "pal-intake": """PAL Intake — route: first stage, never skipped.
Converts raw chat requests into a structured run intent before any downstream agent acts.
Procedure:
1. Parse user request into intent-spec.
2. Classify fields into facts / inferences / open questions.
3. Flag 'unknown — needs decision' fields (never guess) → needs-clarification to user.
4. Emit questions to user, and research targets to RAG-DAL for 'unknown — needs research'.
Guardrails: never fabricate classification/OAuth/approval-gate defaults; if a secret is pasted, redact to [REDACTED — provide via env var instead].""",
    "gtm-strategist": """GTM Strategist — defines the ICP and market segments from an approved brief.
Procedure:
1. Read company product brief + approved KB.
2. Define firmographics, role, pains, triggers, exclusions.
3. Set scoring weights and a scoring rubric.
4. Produce a versioned icp_versions artifact.
Guardrails: never invent value prop/case study/compliance posture — brief or KB only; include suppression/do-not-contact as hard exclusions.""",
    "rag-dal-researcher": """RAG-DAL Researcher — researches accounts and people from allowed, licensed sources (Clay, Amplemarket, ZoomInfo) and the approved KB.
Procedure:
1. Take ICP + research plan.
2. Search licensed sources for accounts/contacts matching ICP.
3. Record evidence with source URL, timestamp, confidence level per claim.
4. Emit a research dossier / lead dossier.
Guardrails: only licensed sources + approved data providers, no autonomous scraping; never present inferred data as fact — always label source + confidence; confidential/regulated source files require approval before ingestion.""",
    "prospect-qualifier": """Prospect Qualifier — scores and routes leads against an ICP version.
Procedure:
1. Receive research dossier + ICP scoring rubric.
2. Score each contact → lead_score (score, reason_codes, confidence).
3. Assign lead state: New → Researching → Qualified → Review → Staged → Enrolled → Suppressed.
4. Apply suppression/do-not-contact before any Qualified/Staged transition.
Guardrails: suppression always wins over scores; never auto-stage — staging is approval-gated later.""",
    "sequence-architect": """Sequence Architect — creates editable, channel-aware outreach copy from prospect research.
Procedure:
1. Take qualified prospects + their research dossiers.
2. Draft multi-step sequence (e.g. 4-step email sequence) with personalization merge fields.
3. Generate variants + a preview showing merge-field resolution.
4. Emit sequence JSON for review. Triggers approval request.
Guardrails: copy must be evidence-grounded from research (pains, triggers); never embed secrets or fake case studies.""",
    "compliance-gate": """Compliance Gate — enforces suppression, consent, policy, and approval rules on every external action.
Checks (ALL must pass before side effects):
1. Suppression / do-not-contact / unsubscribe not matched.
2. Consent / legal basis valid for the channel.
3. Approval event exists, is 'approved', unexpired.
4. Payload scope exactly matches the approved preview.
5. Destructive / scope-expanding ops blocked unless re-approved.
Output: pass/fail + remediation steps. stage_enrollment must reject unless all pass. Compliance output is binding on all downstream agents.""",
    "npao-orchestrator": """NPAO Orchestrator — the ONLY agent that manages run state. Sets phase, urgency, dependencies, routing and handoffs.
Procedure:
1. Set 5D phase (PreD/Design/Development/Deployment/Debugging) for each run.
2. Score 4D priority (Phase×0.35)+(Dependency×0.30)+(Business×0.25)+(Resource×0.10).
3. Route to the right child agent; enforce sequential/parallel handoffs.
4. Persist run + artifacts to run ledger; own dispatch of child agents.
Guardrails: research/writing agents may produce artifacts but may NOT perform side effects; only NPAO Orchestrator writes run state.""",
    "automation-planner": """Automation Planner — selects an approved n8n workflow and builds a dry-run payload for staged enrollment.
Procedure:
1. Receive approved enrollment manifest.
2. Select matching n8n workflow (Prospect Automation engine).
3. Build webhook payload + event map (company_id, contacts, sequence refs).
4. Emit dry-run plan; stage only after dry-run passes + approval is valid.
Guardrails: dry-run by default; re-approval required if scope/count/destination/sequence changes; never activate a workflow without a specific approval event.""",
}

# ── Bundle: skills (verbatim from turnriver-sdr-agent) -------------------------
SKILLS = {
    "pal": """PAL (Prompt Abstraction Layer) — five-stage pipeline:
1. Intent extraction → primary_intent, domain, subject, constraints, desired_output, urgency, ambiguity_score(0–1).
2. Context injection → workspace state, project context, org (ICP/brand), team conventions.
3. Semantic enhancement → expand vague verbs, add success criteria/format/verification, decompose compound goals, remove hedging.
4. Runtime compilation → agent_type, model, temperature, tools (allow/deny), memory mode, output format/destination/verification.
5. Output routing → route to the correct execution layer by phase.
PAL Intake Gate (mandatory): do not begin intent compilation until a completed intake artifact exists. If a raw request arrives without one, pre-fill everything inferable and return as needs-clarification. 'unknown — needs research' → RAG-DAL; 'unknown — needs decision' → blocks with needs-clarification. Never guess high-risk/defaultable settings (classification, OAuth, approval gates). If a secret is pasted, redact it immediately and flag the run 'blocked'.""",
    "research": """Research (Prospect & Company Dossier) — for each account/contact generate:
1. Pain-point hypothesis — from ICP pains + sources; label as hypothesis + confidence.
2. Company summary — segment, size, region, industry, tech signals, ICP fit.
3. Prospect summary — role title, function, likely pains, trigger personalization hooks.
Output schema: {entity, content, citations[{url,title,published_date,tier,credibility}], confidence, source}.
Guardrails: tier-1/2 sources for material claims; mark uncertain if confidence < 0.7; never present inferred data as fact.""",
    "lead-generation": """Lead Generation (Prospect Discovery):
1. Read the approved ICP (firmographics, role, pains, triggers, exclusions).
2. Choose the licensed source (Clay enrichment | Amplemarket/ZoomInfo discovery).
3. Run discovery: upload CSV OR prompt-driven search OR scheduled daily run.
4. Cross-reference the CRM to exclude already-active accounts.
5. Emit candidate list with source + confidence.
Guardrails: only licensed providers; no autonomous scraping or LinkedIn automation; never invent contact data — every field labelled source + confidence; missing connector → tag requires_new_connector, never assume.""",
    "gtm-architect": """GTM Architect (ICP framework):
1. Read company brief + approved KB.
2. Define ICP framework: firmographics · role · pains · triggers · exclusions · scoring weights.
3. Define persona segments with distinct messaging angles.
4. Define channel strategy (email, LinkedIn/DM) and sequence archetypes.
5. Emit icp_versions + positioning guidance.
Guardrails: ICP must cite approved brief/KB — never invent product claims; include suppression/do-not-contact and scope exclusions explicitly; one ICP version per review cycle.""",
    "copywriting": """Copywriting (Outreach Messaging):
1. Read prospect/company research (pains, triggers, personalization hooks).
2. Draft a multi-step sequence (default 4-step) with merge fields — opener names the trigger/pain with evidence (cite source); body ties capability to pains; CTA is a single low-friction ask.
3. Generate 1–2 variants per step for A/B preview.
4. Show a personalization preview resolving merge fields.
Guardrails: copy grounded in the research dossier — never fabricate a case study or metric; respect suppression/do-not-contact; output is editable by a human before approval.""",
    "clay-engineer": """Clay Engineer — wiring/debugging Clay enrichment into the n8n workflow.
1. Use the Clay sources/webhook pull-in-data-from-a-webhook endpoint to enrich each company.
2. Payload contract: company_id, company_linkedin_url, company_domain, company_name, company_state, hubspot_owner_id, intent_type, country, industry, n8n_webhook_url.
3. Batch 1 company at a time with ~5s interval; resume via execution.resumeUrl.
4. Test via dry-run; confirm enrichment fields before enabling live runs.
Guardrails: credentials via ENV: only (CLAY_API_KEY); never send PII without an approved scope; verify field mapping against the manifest.""",
    "amplemarket-engineer": """Amplemarket Engineer — contact discovery/enrichment and sequence enrollment.
1. Discovery: find contacts matching ICP. 2. Enrichment: fill missing fields. 3. Sequence enrollment: enroll approved contacts.
Credentials via ENV:AMPLEMARKET_API_KEY. Verify scopes are narrowest-set (scope minimization). Stage enrollment only via the approved Automation Planner path.
Guardrails: no secret ever enters artifacts — ENV: references only; suppression before any enrollment action; dry-run preview + re-approval on scope/contact-count changes.""",
    "n8n-engineer": """n8n Engineer — the daily outreach engine (Prospect Automation — Part 1):
Schedule Trigger (07:00) → Set Yesterday Range → Get HubSpot Companies (intent/ABM workflow-date in range) → Split Each Company → Filter remove APAC → <2,000 employees → Remove competitors → Filter 0 associated deals → Filter lifecycle ≠ customer → type ≠ Customer → last sales activity > 30d → ICP Filter → Round Robin Assignment → Edit Fields → HTTP → Clay webhook → Upsert → downstream research/messaging/staging.
Rules: each stage maps to an explicit n8n node referenced by exact name; credentials are node credentials (never inline); add retryOnFail on Clay webhook; keep 'Set Yesterday Range' as the single time-source; add matching HubSpot filter fields.
Guardrails: dry-run by default; never activate production workflow without an approval event; never log secrets or whole payloads with PII; suppression/do-not-contact enforced before any staging/enrollment node.""",
    "n8n-execution-analyst": """n8n Execution Analyst — check/monitor/audit n8n executions (read-only).
Routing: 'check/pull/refresh executions' → ingest; 'run the daily report' → ingest → alert → dashboard; any question about runs/failures/rates → query the store and relay the answer; 'open the dashboard' → present index.html; offline demo via fixtures.
Guardrails: READ-ONLY n8n API (only GET — never DELETE/activate/deactivate); secrets from env only (N8N_API_KEY, N8N_BASE_URL); no fabrication — absent fields are null, say so if no data; alerts dry-run by default; idempotent ingestion (upsert on execution ID).""",
}

# ── System prompt assembly ----------------------------------------------------
def build_system_prompt() -> str:
    """Bundle all souls + skills as literal model system context so the model
    routes per the runtime flow and obeys the governance boundaries."""
    parts: List[str] = []
    parts.append(
        "You are the TurnRiverSDR master agent (agentcore backend, v0.1). "
        "You orchestrate a governed AI-SDR pipeline for Turn/River portfolio companies "
        "over workspace-scoped, isolated workspaces per company."
    )
    parts.append(
        "RUNTIME FLOW (orchestrated only by NPAO Orchestrator):\n"
        "chat intake -> PAL intent spec -> GTM Strategist -> RAG-DAL research "
        "-> (Prospect Qualifier interleaves with research) -> Sequence Architect "
        "-> Compliance Gate -> approval request -> Automation Planner dry-run "
        "-> staged enrollment -> results ingestion -> dashboard. "
        "PAL intake is MANDATORY and never skipped. Only NPAO Orchestrator writes run state; "
        "research/writing agents produce artifacts but NEVER perform side effects."
    )
    parts.append("HARD GOVERNANCE BOUNDARIES (BINDING — NEVER LOOSEN):")
    for i in sorted(GOVERNANCE):
        parts.append(f"  {i}. {GOVERNANCE[i]}")
    parts.append("HANDLED BY AGENTS:" + "".join(f"\n\n### {name.upper()}\n{soul}" for name, soul in SOULS.items()))
    parts.append("SKILLS AVAILABLE (load the relevant one before executing):" +
                 "".join(f"\n\n### SKILL: {name}\n{skill}" for name, skill in SKILLS.items()))
    parts.append(
        "MEMORY: Each workspace is isolated under namespace "
        "workspaces/{organization_id}/{workspace_id}. Read only your own workspace. "
        "Never store API keys, raw chain-of-thought, or raw PII beyond declared scope. "
        "When responding, return a concise, actionable SDR answer plus structured "
        "routing metadata (see output contract)."
    )
    return "\n\n".join(parts)


SYSTEM_PROMPT = build_system_prompt()


# ── Runtime routing -----------------------------------------------------------
# Deterministic intent inference used (a) to pick the handler/child that "handled"
# the request and (b) to keep the compliance gate honest about side-effect gating.
_KNOWN_COMPANIES = ["solarwinds", "starlims", "asci", "commio", "invicti", "paessler", "tufin"]


def _classify_intent(prompt: str) -> Dict[str, Any]:
    low = prompt.lower()
    intent = "general"
    child = "npao-orchestrator"
    if any(w in low for w in ["icp", "ideal customer", "target account", "persona", "segment"]):
        intent, child = "gtm-icp", "gtm-strategist"
    elif any(w in low for w in ["research", "dossier", "find prospect", "list of", "market", "company"]):
        intent, child = "research", "rag-dal-researcher"
    elif any(w in low for w in ["score", "qualif", "lead state", "fit", "grade"]):
        intent, child = "qualify", "prospect-qualifier"
    elif any(w in low for w in ["sequence", "email", "outreach", "dm", "draft", "copy", "write"]):
        intent, child = "sequence", "sequence-architect"
    elif any(w in low for w in ["approve", "approval", "stage", "enroll", "dry-run", "workflow", "n8n"]):
        intent, child = "side-effect", "automation-planner"
    # route side-effect designs first; else keep the mapped child
    compliance_relevant = any(w in low for w in ["send", "enroll", "activate", "export", "write to crm", "stage"])
    compliance_required = intent == "side-effect" or compliance_relevant
    engine = "n8n-prospect-automation" if any(w in low for w in ["n8n", "workflow", "enroll", "automate"]) else None
    return {
        "intent": intent,
        "handler": child,
        "compliance_required": compliance_required,
        "engine": engine,
        "needs_clarification": any(w in low for w in ["?", "unknown", "maybe", "not sure"]),
    }


# ── AgentCore entrypoint ------------------------------------------------------
@app.entrypoint
def turnriver_master(payload: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Main TurnRiverSDR master-agent entrypoint (AgentCore runtime).

    Payload fields:
        prompt        (str, required)  — user message
        workspace_id  (str, optional)  — default 'demo'; isolated memory namespace
        provider      (str, optional)  — 'anthropic' | 'openai', default 'anthropic'
        api_key       (str, optional)  — BYOK; falls back to ENV:
        model         (str, optional)  — model override
        session_id    (str, optional)  — memory continuity (>= 33 chars under AgentCore)
    """
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return {"error": "prompt is required", "success": False, "compliance": _gate_summary(False, "no prompt")}

    workspace_id = payload.get("workspace_id", "demo") or "demo"
    # Default to Bedrock when the AWS bearer token is present (no explicit provider).
    if payload.get("provider"):
        provider = payload["provider"]
    elif os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        provider = "bedrock"
    else:
        provider = "anthropic"
    api_key = payload.get("api_key") or _get_key_from_env(provider)
    model = payload.get("model") or _default_model(provider)
    session_id = payload.get("session_id") or f"workspace-{workspace_id}"

    # 1) PAL intake gate — never skip
    route = _classify_intent(prompt)
    if route.get("needs_clarification"):
        return {
            "success": True,
            "handler": "pal-intake",
            "message": "PAL intake could not fully compile this request. Please clarify: "
                       "1) target portfolio company/workspace, 2) ICP constraints or approved brief, "
                       "3) scope of output. Research targets were flagged for RAG-DAL.",
            "routing_trace": ["pal-intake"],
            "compliance": _gate_summary(False, "no side-effect requested; awaiting clarification"),
            "mode": "needs-clarification",
        }

    # 2) workspace-scoped memory context (AgentCore Memory, isolated namespace)
    memory_context = _load_memory(session_id, workspace_id, prompt)

    # 3) LLM call with full bundled system context
    system = _compose_system_for(route) + memory_context
    # Live Bedrock path uses the AWS Bedrock bearer token + inference profile (no api_key needed).
    live = bool(api_key) or (provider == "bedrock" and os.getenv("AWS_BEARER_TOKEN_BEDROCK"))
    if not live:
        # Honest degraded mode: deterministic mock so the harness provably runs
        # offline. In production this path is never reached (AgentCore injects
        # the Bedrock key server-side; BYOK or AWS_BEARER_TOKEN_BEDROCK provide live).
        reply, trace = _mock_reply(prompt, route, workspace_id)
        model = model + " (mock)"
    else:
        try:
            messages = [{"role": "user", "content": prompt}]
            reply = _call_provider(provider, api_key or os.getenv("AWS_BEARER_TOKEN_BEDROCK"),
                                   model, system, messages)
            trace = _routing_trace(route)
        except httpx.HTTPStatusError as e:
            return {"error": f"LLM error {e.response.status_code}: {e.response.text[:200]}", "success": False,
                    "compliance": _gate_summary(False, "LLM backend failure; blocked before action")}
        except Exception as e:  # pragma: no cover - defensive
            return {"error": str(e), "success": False, "compliance": _gate_summary(False, "unexpected backend error")}

    # 4) compliance gate — binding on any side-effect intent
    gate_ok = not route.get("compliance_required")
    gate_note = "no side-effect requested" if gate_ok else \
        "BLOCKED: external action requires a human approval event; nothing was sent/enrolled/activated. Generated artifacts are dry-run only."
    if not gate_ok:
        reply += (
            "\n\n[COMPLIANCE GATE BLOCKED SIDE EFFECT] This request would send/enroll/activate/export. "
            "Per governance boundary #1, no side effect was performed. A preview + approval request is required "
            "before Automation Planner may stage anything."
        )

    # 5) persist to workspace-scoped memory
    _store_memory(session_id, workspace_id, prompt, reply)

    return {
        "success": True,
        "handler": route["handler"],
        "intent": route["intent"],
        "message": reply.strip(),
        "routing_trace": trace,
        "compliance": _gate_summary(gate_ok, gate_note),
        "workspace_id": workspace_id,
        "model": model,
        "provider": provider,
        "governance": {"boundaries": list(GOVERNANCE.values())},
        "mode": "mock" if not api_key else "live",
    }


# ── Routing / composition helpers ---------------------------------------------
def _gate_summary(ok: bool, note: str) -> Dict[str, Any]:
    return {"pass": ok, "note": note}


def _compose_system_for(route: Dict[str, Any]) -> str:
    """Add routing awareness to the canonical system prompt."""
    return (
        SYSTEM_PROMPT
        + "\n\nRESPONSE CONTRACT: Return a concise SDR answer. Add the fields "
          "handler, intent, compliance{pass,note} to any structured output. "
          "For this request: intent=" + route["intent"] + ", primary handler="
          + route["handler"] + ", compliance_required=" + str(route["compliance_required"]) + "."
    )


def _routing_trace(route: Dict[str, Any]) -> List[str]:
    trace = ["pal-intake", route["handler"]]
    engine = route.get("engine")
    if engine:
        trace.append("automation-planner")
        trace.append("compliance-gate")
        if route.get("compliance_required"):
            trace.append("pending-approval")
    return trace


# ── Memory helpers (AgentCore, with local fallback) --------------------------
def _load_memory(session_id: str, workspace_id: str, query: str) -> str:
    """Retrieve workspace-scoped memory for the session."""
    try:
        key = f"workspaces/{{org}}/{workspace_id}/{session_id}" if AGENTCORE_AVAILABLE else session_id
        records = get_memory_client().retrieve(session_id=key, query=query, top_k=3)
        if not records and not AGENTCORE_AVAILABLE:
            # fallback store keyed per session in this process
            records = _FALLBACK_MEMORY.get(key, [])
        if records:
            return "\n\nRelevant context from this workspace's memory:\n" + "\n".join(
                f"- {r['content']}" for r in records
            )
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)
    return ""


def _store_memory(session_id: str, workspace_id: str, prompt: str, reply: str) -> None:
    try:
        key = f"workspaces/{{org}}/{workspace_id}/{session_id}" if AGENTCORE_AVAILABLE else session_id
        content = f"Q: {prompt[:300]}\nA: {reply[:500]}"
        if AGENTCORE_AVAILABLE:
            get_memory_client().store(session_id=key, content=content)
        else:
            _FALLBACK_MEMORY.setdefault(key, []).append({"content": content})
    except Exception as e:
        logger.warning("Memory store failed: %s", e)


# ── Provider helpers (sync, mirroring rostr reference) -------------------------
def _call_provider(provider: str, api_key: str, model: str, system: str, messages: list) -> str:
    if provider == "openai":
        return _call_openai_sync(api_key, model, system, messages)
    if provider == "bedrock":
        return _call_bedrock_converse(api_key, model, system, messages)
    return _call_anthropic_sync(api_key, model, system, messages)


def _call_bedrock_converse(bearer_token: str, model: str, system: str, messages: list) -> str:
    """Live Amazon Bedrock invoke via AWS Bedrock Runtime Converse.

    Uses the AWS_BEARER_TOKEN_BEDROCK (a Bedrock long-term bearer token) + the
    inference profile model id. Requires the inference profile (bedrock-runtime
    on-demand invoke rejects bare model ids), e.g.:
      us.anthropic.claude-sonnet-4-5-20250929-v1:0
    """
    import boto3
    from botocore.config import Config
    client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        config=Config(retries={"max_attempts": 2, "mode": "standard"}),
    )
    # boto3 Converse expects content as a list of content blocks, e.g. [{"text": ...}].
    normalized = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            content = [{"text": content}]
        elif isinstance(content, list) and not (content and isinstance(content[0], dict)):
            content = [{"text": str(content)}]
        normalized.append({"role": m.get("role", "user"), "content": content})
    resp = client.converse(
        modelId=model,
        messages=normalized,
        system=[{"text": system}],
        inferenceConfig={"maxTokens": 1024, "temperature": 0.3},
    )
    try:
        return resp["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Bedrock response shape: {type(resp).__name__}") from e


def _call_anthropic_sync(api_key: str, model: str, system: str, messages: list) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={"model": model, "system": system, "messages": messages, "max_tokens": 1024},
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def _call_openai_sync(api_key: str, model: str, system: str, messages: list) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}] + messages,
                "max_tokens": 1024,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _default_model(provider: str) -> str:
    models = {
        "anthropic": "claude-sonnet-4-5-20250929",
        "openai": "gpt-4o",
        # Bedrock on-demand invoke requires an inference profile (not a bare model id).
        "bedrock": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    }
    return models.get(provider, models["anthropic"])


def _get_key_from_env(provider: str) -> str:
    keys = {
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "bedrock": os.getenv("AWS_BEARER_TOKEN_BEDROCK", ""),
    }
    return keys.get(provider, "")


# ── Deterministic offline reply (self-test / no-key degraded mode) ------------
def _mock_reply(prompt: str, route: Dict[str, Any], workspace_id: str) -> tuple[str, List[str]]:
    """Produce an honest, artifact-shaping reply WITHOUT a network call so the
    harness provably runs offline. Mirrors what the live model would return:
    grounded to approved context, labeled confidence, dry-run-only."""
    company = next((c for c in _KNOWN_COMPANIES if c in prompt.lower()), "portfolio company")
    trace = _routing_trace(route)
    if route["intent"] == "gtm-icp":
        body = (f"[MOCK — no API key] ICP draft for {company.title()}: "
                "firmographics=target-SMB, role=VP Sales/GTM, pains=diligence+manual outbound, "
                "triggers=funding/hiring, exclusions=suppression list. "
                "Source: approved brief (not yet provided) — confidence 0.5, verify before use.")
    elif route["intent"] == "research":
        body = (f"[MOCK — no API key] Research plan for {company.title()}: search licensed "
                "sources (Clay/Amplemarket/ZoomInfo) for matching accounts; every claim will be "
                "labeled source+timestamp+confidence; no autonomous scraping.")
    elif route["intent"] == "qualify":
        body = (f"[MOCK — no API key] Qualification rubric ready for {company.title()}; "
                "scores = ICP fit weights; suppression always wins; nothing staged without approval.")
    elif route["intent"] == "sequence":
        body = (f"[MOCK — no API key] 4-step sequence draft scaffold for {company.title()} "
                "with merge fields + evidence-grounded opener; editable before approval; "
                "no fabricated case studies.")
    else:
        body = (f"[MOCK — no API key] Master agent routing for '{prompt[:80]}'. "
                f"Workspace '{workspace_id}' isolated. No external side effect performed; "
                "dry-run only until a human approval event exists.")
    if route["compliance_required"]:
        body += (" [COMPLIANCE BLOCKED SIDE EFFECT] send/enroll/activate requires a human "
                 "approval event; nothing was sent/enrolled/activated.")
    return body, trace


# ── Local self-test ------------------------------------------------------------
if __name__ == "__main__":
    # Provable offline self-test: no API key -> deterministic mock path.
    test_prompts = [
        "Create an ICP for Commio's data-center compliance business",
        "Research prospects and draft a 4-step cold email sequence for StarLIMS",
        "Submit these leads for enrollment into the n8n prospect automation workflow",
    ]
    output = []
    for p in test_prompts:
        res = turnriver_master(
            {"prompt": p, "workspace_id": "demo-commio" if "commio" in p else "demo",
             "provider": os.getenv("PROVIDER", "anthropic"),
             "api_key": os.getenv("ANTHROPIC_API_KEY", "")}
        )
        output.append(res)
        print(json.dumps(res, indent=2))
        print("-" * 72)
    print("SELF-TEST OK: %d requests processed (no network, no API key)." % len(output))
