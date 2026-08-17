# Skill — PAL (Prompt Abstraction Layer)
Use when: turning a raw user request into a structured, unambiguous instruction before any downstream agent acts.

## Five-stage pipeline
1. **Intent extraction** → `primary_intent`, `domain`, `subject`, `constraints`, `desired_output`, `urgency`, `ambiguity_score(0–1)`.
2. **Context injection** → load workspace state, project context, org (ICP/brand), team conventions.
3. **Semantic enhancement** → expand vague verbs, add success criteria/format/verification, decompose compound goals, remove hedging.
4. **Runtime compilation** → agent_type, model, temperature, tools (allow/deny), memory mode, output format/destination/verification.
5. **Output routing** → route to the correct execution layer by phase.

## PAL Intake Gate (mandatory)
Do NOT begin intent compilation until a completed intake artifact exists. If a raw request
arrives without one, pre-fill everything inferable and return as `needs-clarification`.
Never proceed on inference alone for the classification / OAuth / approval-gate sections.
- `unknown — needs research` → RAG-DAL.
- `unknown — needs decision` → blocks with `needs-clarification`.
- Run intake-security before tool-mapping; its output is binding downstream.

## Guardrails
- Always route through PAL — never raw prompts.
- Never guess high-risk/defaultable settings (classification, OAuth, approval gates).
- If a secret is pasted, redact it immediately and flag the run `blocked`.
