"""Lab 05: RAG - historical incidents as CONTEXT for a local LLM, never as proof."""
from config import EMBED_MODEL, LLM_MODEL, LLM_PROVIDER, SIMILARITY_THRESHOLD
from providers import chat
from search import find_similar

current_incident = """Incident: INC-NEW
SID: HXP
Domain: backup
Database: HANA
Title: HANA Backup Failure
Signals: data backup failed at 02:00, backint exit code non-zero,
backint.log contains 'SSL routines: certificate verify failed'"""

candidates = find_similar(current_incident, "backup", "HANA")
history = [c for c in candidates if c["similarity"] >= SIMILARITY_THRESHOLD]

if history:
    context = "\n\n".join(
        f"Similar incident #{i + 1}: {h['incident_id']} on {h['sid']} ({h['incident_date']}), "
        f"similarity {h['similarity']:.2f}\n"
        f"Title: {h['title']}\nEvidence: {h['evidence']}\n"
        f"Root cause status: {h['root_cause_status']}\nResolution: {h['resolution']}"
        for i, h in enumerate(history)
    )
else:
    context = "No sufficiently similar historical incidents found."

system_prompt = """You are an SAP operations investigation assistant.
Historical incidents are CONTEXT ONLY. Similarity does NOT prove the same root cause.
Use history to decide what to check next, never as proof."""

user_prompt = f"""CURRENT EVIDENCE
{current_incident}

HISTORICAL CONTEXT
{context}

Task: propose up to 3 next investigation steps for the CURRENT incident.
Only include steps that fit the current evidence. Fewer steps are better than weak ones.
Do not propose checks that the current evidence already rules out.
For each step, say which historical case inspired it, or "none" if it comes from the current evidence only.
State clearly what must still be verified on the current system."""

answer = chat(system_prompt, user_prompt)

print(f"LLM: {LLM_MODEL} ({LLM_PROVIDER}) | embeddings: {EMBED_MODEL} | threshold: {SIMILARITY_THRESHOLD}")
print("--- HISTORICAL CONTEXT ---")
print(context)
print("\n--- MODEL ANSWER ---")
print(answer)