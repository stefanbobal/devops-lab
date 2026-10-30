"""Lab 05: RAG with calibrated retrieval thresholds and local/cloud LLMs."""
import argparse
import json
import math
import os
from pathlib import Path


def load_threshold(profile, path):
    """Read exactly one valid per-profile threshold; never silently use 0.60."""
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read thresholds from {path}: {exc}") from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected a list of profile records")
    matches = [row for row in rows if row.get("model") == profile]
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one threshold for {profile!r}, found {len(matches)}")
    value = matches[0].get("threshold")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: threshold for {profile!r} must be numeric")
    if not math.isfinite(value) or not -1 <= value <= 1:
        raise ValueError(f"{path}: threshold for {profile!r} must be finite and in [-1, 1]")
    return float(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thresholds-file", type=Path,
                        default=Path(__file__).with_name("thresholds_FROZEN.json"),
                        help="Threshold JSON (default: thresholds_FROZEN.json next to rag.py)")
    parser.add_argument("--threshold", type=float,
                        help="Explicit experimental override; bypasses the threshold JSON")
    args = parser.parse_args()
    from config import EMBED_MODEL, LLM_MODEL, LLM_PROVIDER, PROFILE
    if args.threshold is None:
        try:
            threshold = load_threshold(PROFILE, args.thresholds_file)
        except ValueError as exc:
            parser.error(str(exc))
        source = str(args.thresholds_file.resolve())
    else:
        threshold = args.threshold
        if not math.isfinite(threshold) or not -1 <= threshold <= 1:
            parser.error("--threshold must be finite and in [-1, 1]")
        source = "explicit --threshold override"
    if os.getenv("SIMILARITY_THRESHOLD") is not None:
        print("Note: RAG ignores SIMILARITY_THRESHOLD; use --threshold for an explicit override.")
    if LLM_PROVIDER == "azure":
        if not LLM_MODEL:
            parser.error("Set AZURE_OPENAI_LLM_DEPLOYMENT to the Azure chat deployment name.")
        for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
            if not os.getenv(name, "").strip():
                parser.error(f"Set {name} before using Azure OpenAI.")
    from providers import chat
    from search import find_similar

    current_incident = """Incident: INC-NEW
SID: HXP
Domain: backup
Database: HANA
Title: HANA Backup Failure
Signals: data backup failed at 02:00, backint exit code non-zero,
backint.log contains 'SSL routines: certificate verify failed'"""

    print(f"Embedding profile: {PROFILE} | threshold: {threshold} | source: {source}")

    candidates = find_similar(current_incident, "backup", "HANA")
    history = [c for c in candidates if c["similarity"] >= threshold]

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

    print(f"LLM: {LLM_MODEL} ({LLM_PROVIDER}) | embeddings: {EMBED_MODEL} | threshold: {threshold}")
    print("--- HISTORICAL CONTEXT ---")
    print(context)
    print("\n--- MODEL ANSWER ---")
    print(answer)


if __name__ == "__main__":
    main()
