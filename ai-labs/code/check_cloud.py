"""Small paid API probes before evaluation; run on the configured Ubuntu VM."""
import os
import subprocess
import sys
from pathlib import Path

TESTS = [
    ("embedding gemini", {"EMBED_PROFILE": "gemini"},
     "from config import EMBED_MODEL; print('Model:', EMBED_MODEL, flush=True); "
     "from providers import embed; v = embed('HANA backup failed', 'query'); "
     "print(f'OK, {len(v)} dims')"),
    ("embedding azure", {"EMBED_PROFILE": "azure"},
     "from config import EMBED_MODEL; print('Model:', EMBED_MODEL, flush=True); "
     "from providers import embed; v = embed('HANA backup failed', 'query'); "
     "print(f'OK, {len(v)} dims')"),
]
for profile in ("claude", "haiku", "opus", "gemini", "azure"):
    TESTS.append((
        f"LLM {profile}", {"LLM_PROFILE": profile},
        "from config import LLM_MODEL, LLM_PROVIDER; "
        "print(f'Model/deployment: {LLM_MODEL} | provider: {LLM_PROVIDER}', flush=True); "
        "from providers import chat; "
        "answer = chat('Answer in one short sentence.', 'Say hello in Slovak.'); "
        "assert isinstance(answer, str) and answer.strip(), 'Empty answer'; "
        "print('OK:', answer)"
    ))


def main():
    failures = 0
    for name, env, code in TESTS:
        print(f"\n--- {name} ---", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                env={**os.environ, **env},
                cwd=Path(__file__).resolve().parent,
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            failures += 1
            print("FAILED: timed out after 180 seconds")
            continue
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode:
            failures += 1
            print(f"FAILED (exit {result.returncode})")
            print(result.stderr.strip() or "No error details returned.")
        elif result.stderr.strip():
            print(result.stderr.strip())
    print(f"\nCompleted: {len(TESTS) - failures} passed, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
