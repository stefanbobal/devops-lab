"""Validate result directories; --execute imports them atomically into llm_eval."""
import argparse
import os
import sys
from pathlib import Path
from db_store import collect_runs, connect, init_schema, import_runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True,
                        help="A run directory or parent results directory")
    parser.add_argument("--execute", action="store_true", help="Create schema if absent and import")
    args = parser.parse_args(argv)
    try:
        runs, warnings = collect_runs(args.results)
        for run in runs:
            print(run["name"], "|", len(run["calls"]), "calls |", len(run["contexts"]), "contexts | id:", run["id"])
        for warning in warnings:
            print("NOTE:", warning)
        if not args.execute:
            print("Dry run: files validated; no database connection or changes.")
            return 0
        with connect() as conn:
            init_schema(conn)
            counts = import_runs(conn, runs, os.getenv("LAB_REVIEWER", "sapops"))
        print("Committed:", counts)
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print("Import rejected:", type(exc).__name__, "-", str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Database errors may contain a credential-bearing DSN; do not print them.
        print("Database import failed:", type(exc).__name__, "- transaction rolled back; check DB access and privileges", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
