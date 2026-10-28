"""Lab 06b: score every embedding model at several thresholds and show the best one.

Each query is embedded only once per model (top result + its score are cached),
then the thresholds are applied offline - so cloud models are not called again per threshold.
Usage: python sweep_eval.py [profile ...]
"""
import ast
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

THRESHOLDS = [
    0.30, 0.35, 0.40, 0.45, 0.50, 0.55,
    0.60, 0.65, 0.70, 0.75, 0.80, 0.85,
]


def load_tests():
    """Read the TESTS list from eval.py without running eval.py."""
    tree = ast.parse(Path(__file__).with_name("eval.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "TESTS":
            return ast.literal_eval(node.value)
    raise SystemExit("TESTS not found in eval.py")


def top_results():
    """Runs inside one model profile: print the best match and score for every test."""
    from search import find_similar
    for query, domain, db_type, _ in load_tests():
        r = find_similar(query, domain, db_type, limit=1)[0]
        print(f"{r['incident_id']}\t{r['similarity']:.4f}")


def best_threshold_range(scores):
    best_score = max(scores)
    best_indices = [i for i, score in enumerate(scores) if score == best_score]
    ranges = []
    start = previous = best_indices[0]
    for index in best_indices[1:]:
        if index != previous + 1:
            ranges.append((start, previous))
            start = index
        previous = index
    ranges.append((start, previous))

    start, end = max(ranges, key=lambda span: (span[1] - span[0] + 1, -span[0]))
    midpoint = start + (end - start) // 2
    return THRESHOLDS[midpoint], THRESHOLDS[start], THRESHOLDS[end], best_score


if len(sys.argv) > 1 and sys.argv[1] == "--worker":
    top_results()
    sys.exit()

profiles = sys.argv[1:] or [
    "nomic", "nomic_prefix", "bge", "qwen", "qwen8", "qwen_instr", "gemini", "azure",
]
tests = load_tests()
thresholds_path = Path(__file__).with_name("thresholds.json")
if thresholds_path.exists():
    try:
        stored_thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Could not parse {thresholds_path.name}: {error}")
    if not isinstance(stored_thresholds, list):
        raise SystemExit(f"Expected a list of model entries in {thresholds_path.name}")
else:
    stored_thresholds = []
thresholds_by_model = {entry["model"]: entry for entry in stored_thresholds}
updated_models = set()
header = "model     " + "".join(f"{t:>7.2f}" for t in THRESHOLDS) + "    best"
print(header)
print("-" * len(header))
for profile in profiles:
    out = subprocess.run([sys.executable, __file__, "--worker"], capture_output=True, text=True,
                         env={**os.environ, "EMBED_PROFILE": profile})
    if out.returncode != 0:
        print(f"{profile:<10}ERROR: {out.stderr.strip().splitlines()[-1]}")
        continue
    results = [line.split("\t") for line in out.stdout.strip().splitlines()]
    scores = []
    for threshold in THRESHOLDS:
        correct = 0
        for (found, sim), (_, _, _, expected) in zip(results, tests):
            hit = found if float(sim) >= threshold else None
            correct += (hit is None) if expected is None else (hit in expected)
        scores.append(correct)
    best_t, range_from, range_to, best = best_threshold_range(scores)
    row = "".join(f"{s:>7}" for s in scores)
    print(f"{profile:<10}{row}    {best}/{len(tests)} at {best_t:.2f} "
          f"(best range {range_from:.2f}-{range_to:.2f})")
    thresholds_by_model[profile] = {
        "model": profile,
        "threshold": best_t,
        "range_from": range_from,
        "range_to": range_to,
        "score": best,
        "date": date.today().isoformat(),
    }
    updated_models.add(profile)

if updated_models:
    ordered = [thresholds_by_model[model] for model in sorted(thresholds_by_model)]
    thresholds_path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    print(f"\nUpdated {thresholds_path.name} for: {', '.join(sorted(updated_models))}")
