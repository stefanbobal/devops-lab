"""Lab 05: RAG - historical incidents as CONTEXT for a local LLM, never as proof."""
import ollama

from config import LLM_MODEL, SIMILARITY_THRESHOLD
from search import find_similar

current_incident = """SID: D60
Domain: backup
Database: HANA
Title: HANA Backup Failure
Signals: data backup failed at 02:00, backint exit code non-zero,
backint.log contains 'SSL routines: certificate verify failed'"""

candidates = find_similar(current_incident, "backup", "HANA")
history = [c for c in candidates if c["similarity"] >= SIMILARITY_THRESHOLD]

if history:
    context = "\n\n".join(
        f"Similar incident #{i + 1}: {h['sid']} ({h['incident_date']}), "
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

Task: propose the 3 most useful next investigation steps for the CURRENT incident.
For each step, say which historical case inspired it.
State clearly what must still be verified on the current system."""

response = ollama.chat(model=LLM_MODEL, messages=[
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt},
])

print("--- HISTORICAL CONTEXT ---")
print(context)
print("\n--- MODEL ANSWER ---")
print(response["message"]["content"])
