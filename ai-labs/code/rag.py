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

    from rag_prompt import format_context, build_prompts
    context = format_context(history)
    system_prompt, user_prompt = build_prompts(current_incident, context)

    answer = chat(system_prompt, user_prompt)

    print(f"LLM: {LLM_MODEL} ({LLM_PROVIDER}) | embeddings: {EMBED_MODEL} | threshold: {threshold}")
    print("--- HISTORICAL CONTEXT ---")
    print(context)
    print("\n--- MODEL ANSWER ---")
    print(answer)


if __name__ == "__main__":
    main()

