"""Shared prompt for the single-incident demo and matrix evaluation."""
SYSTEM_PROMPT = """You are an SAP operations investigation assistant.
Historical incidents are CONTEXT ONLY. Similarity does NOT prove the same root cause.
Use history to decide what to check next, never as proof."""


def format_context(history):
    if not history:
        return "No sufficiently similar historical incidents found."
    return "\n\n".join(
        f"Similar incident #{i + 1}: {h['incident_id']} on {h['sid']} ({h['incident_date']}), "
        f"similarity {h['similarity']:.2f}\n"
        f"Title: {h['title']}\nEvidence: {h['evidence']}\n"
        f"Root cause status: {h['root_cause_status']}\nResolution: {h['resolution']}"
        for i, h in enumerate(history))


def build_prompts(current_incident, context):
    return SYSTEM_PROMPT, f"""CURRENT EVIDENCE
{current_incident}

HISTORICAL CONTEXT
{context}

Task: propose up to 3 next investigation steps for the CURRENT incident.
Only include steps that fit the current evidence. Fewer steps are better than weak ones.
Do not propose checks that the current evidence already rules out.
For each step, say which historical case inspired it, or "none" if it comes from the current evidence only.
State clearly what must still be verified on the current system."""
