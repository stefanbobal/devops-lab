"""Per-profile retrieval thresholds; never silently fall back to a default."""
import json
import math
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
