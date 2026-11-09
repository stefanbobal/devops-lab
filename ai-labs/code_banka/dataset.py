"""Which data set a test reads, with one guard for the held-out set (step F).

Shared by t3_chain.py, t3_spec.py and t1_extraction.py, same rule as t2_retrieval.py:
`--set test` is refused unless `--final` is also given, so the held-out data_test/ is never touched by accident
and never used for tuning. Without `--set` the dev set (data/) is used, as before.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent
SETS = {"dev": BASE / "data", "test": BASE / "data_test"}


def choose_set(argv):
    """Return (name, folder) for --set dev|test; the test set needs --final."""
    name = "dev"
    if "--set" in argv:
        i = argv.index("--set")
        if i + 1 >= len(argv):
            raise SystemExit("--set needs a value: dev or test")
        name = argv[i + 1]
    if name not in SETS:
        raise SystemExit(f"--set must be one of {', '.join(SETS)}, got {name!r}")
    if name == "test" and "--final" not in argv:
        raise SystemExit("The test set is held out: tuning on it is not allowed. Add --final to evaluate once.")
    return name, SETS[name]


def strip_set_flags(argv):
    """argv without --set <name> and --final, for scripts whose other arguments are positional."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
        elif a == "--set":
            skip = True
        elif a != "--final":
            out.append(a)
    return out
