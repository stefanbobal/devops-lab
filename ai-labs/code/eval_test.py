"""Evaluate the held-out questions once using thresholds selected by sweep_eval.py.

Usage: python eval_test.py [profile ...]
With no profiles specified, every model in thresholds.json is evaluated.
"""
import csv
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from test_questions import TESTS

KINDS = ("normal", "paraphrase", "trap", "slovak", "nothing")
TOP_K = 3
CSV_FIELDS = (
    "model", "date", "set", "kind", "threshold", "question_count",
    "correct_rank1", "correct_top3", "nonsense_correctly_rejected",
    "nonsense_accepted", "irrelevant_in_context", "gap", "overall_correct",
)


def load_thresholds():
    path = Path(__file__).with_name("thresholds.json")
    if not path.exists():
        raise SystemExit("thresholds.json not found; run sweep_eval.py first")
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Could not parse thresholds.json: {error}")
    if not isinstance(entries, list):
        raise SystemExit("thresholds.json must contain a list of model entries")
    thresholds = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("model"), str):
            raise SystemExit("Each thresholds.json entry must include a model name")
        if "threshold" not in entry:
            raise SystemExit(f"thresholds.json has no threshold for model {entry['model']}")
        thresholds[entry["model"]] = entry["threshold"]
    return thresholds


def fetch_results():
    from search import find_similar

    results = []
    for question, domain, db_type, _expected, _kind in TESTS:
        matches = find_similar(question, domain, db_type, limit=TOP_K)
        results.append([
            {"incident_id": match["incident_id"], "similarity": float(match["similarity"])}
            for match in matches
        ])
    print(json.dumps(results))


def new_metrics():
    return {
        "question_count": 0,
        "correct_rank1": 0,
        "correct_top3": 0,
        "nonsense_correctly_rejected": 0,
        "nonsense_accepted": 0,
        "irrelevant_in_context": 0,
        "overall_correct": 0,
        "weakest_correct_score": None,
        "best_nonsense_score": None,
    }


def update_metrics(metrics, test, matches, threshold):
    _question, _domain, _db_type, expected, _kind = test
    metrics["question_count"] += 1
    above_threshold = [match for match in matches if match["similarity"] >= threshold]
    found = above_threshold[0]["incident_id"] if above_threshold else None
    metrics["overall_correct"] += (
        (found is None) if expected is None else (found in expected)
    )

    if expected is None:
        if above_threshold:
            metrics["nonsense_accepted"] += 1
        else:
            metrics["nonsense_correctly_rejected"] += 1
        if matches:
            score = max(match["similarity"] for match in matches)
            current = metrics["best_nonsense_score"]
            metrics["best_nonsense_score"] = score if current is None else max(current, score)
        return

    if matches and matches[0]["incident_id"] in expected:
        metrics["correct_rank1"] += 1
    if any(match["incident_id"] in expected for match in matches):
        metrics["correct_top3"] += 1

    correct_scores = [m["similarity"] for m in matches if m["incident_id"] in expected]
    if correct_scores:
        best_for_question = max(correct_scores)
        current = metrics["weakest_correct_score"]
        metrics["weakest_correct_score"] = (
            best_for_question if current is None else min(current, best_for_question)
        )

    metrics["irrelevant_in_context"] += sum(
        match["incident_id"] not in expected for match in above_threshold
    )


def summarize(results, threshold):
    summaries = {"all": new_metrics(), **{kind: new_metrics() for kind in KINDS}}
    for test, matches in zip(TESTS, results):
        kind = test[4]
        if kind not in KINDS:
            raise SystemExit(f"Unknown test question kind: {kind}")
        update_metrics(summaries["all"], test, matches, threshold)
        update_metrics(summaries[kind], test, matches, threshold)

    for metrics in summaries.values():
        correct_score = metrics.pop("weakest_correct_score")
        nonsense_score = metrics.pop("best_nonsense_score")
        metrics["gap"] = (
            correct_score - nonsense_score
            if correct_score is not None and nonsense_score is not None
            else None
        )
    return summaries


def append_csv(rows):
    path = Path(__file__).with_name("results.csv")
    write_header = not path.exists() or path.stat().st_size == 0
    if not write_header:
        with path.open(newline="", encoding="utf-8") as file:
            existing_fields = next(csv.reader(file), [])
        if existing_fields != list(CSV_FIELDS):
            raise SystemExit("results.csv has an unexpected header; refusing to append")
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def already_evaluated(profiles):
    path = Path(__file__).with_name("results.csv")
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        done = {row["model"] for row in csv.DictReader(file) if row["set"] == "test"}
    return sorted(done & set(profiles))

def main():
    thresholds = load_thresholds()
    profiles = sys.argv[1:] or list(thresholds)
    if not profiles:
        raise SystemExit("thresholds.json has no model entries; run sweep_eval.py first")
    missing = [profile for profile in profiles if profile not in thresholds]
    if missing:
        raise SystemExit(
            "thresholds.json has no entry for model(s): " + ", ".join(missing)
            + "; run sweep_eval.py for those profiles first"
        )

    repeated = already_evaluated(profiles)
    if repeated:
        raise SystemExit("Test set already evaluated for: " + ", ".join(repeated))

    csv_rows = []
    for profile in profiles:
        result = subprocess.run(
            [sys.executable, __file__, "--worker"],
            capture_output=True,
            text=True,
            env={**os.environ, "EMBED_PROFILE": profile},
        )
        if result.returncode != 0:
            raise SystemExit(
                f"Evaluation failed for model {profile} (exit code {result.returncode}); "
                "provider error details omitted to avoid exposing credentials"
            )
        try:
            matches = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise SystemExit(f"Model {profile} returned invalid evaluation output")
        if len(matches) != len(TESTS):
            raise SystemExit(
                f"Model {profile} returned {len(matches)} results for {len(TESTS)} questions"
            )

        threshold = thresholds[profile]
        summaries = summarize(matches, threshold)
        print(f"\nModel: {profile} | test threshold: {threshold:.2f}")
        for kind, metrics in summaries.items():
            count = metrics["question_count"]
            gap = "n/a" if metrics["gap"] is None else f"{metrics['gap']:.4f}"
            print(
                f"{kind:<12} overall={metrics['overall_correct']}/{count} "
                f"rank1={metrics['correct_rank1']} top3={metrics['correct_top3']} "
                f"nonsense_rejected={metrics['nonsense_correctly_rejected']} "
                f"nonsense_accepted={metrics['nonsense_accepted']} "
                f"irrelevant_in_context={metrics['irrelevant_in_context']} gap={gap}"
            )
            csv_rows.append({
                "model": profile,
                "date": date.today().isoformat(),
                "set": "test",
                "kind": kind,
                "threshold": threshold,
                **metrics,
            })

    append_csv(csv_rows)
    print("\nAppended test metrics to results.csv")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        fetch_results()
    else:
        main()