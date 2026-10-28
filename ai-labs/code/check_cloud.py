"""Smoke test: one tiny call to each cloud model, so problems show up before the real tests."""
import os
import subprocess
import sys

TESTS = [
    ("embedding gemini", {"EMBED_PROFILE": "gemini"},
     "from providers import embed; v = embed('HANA backup failed', 'query'); print(f'OK, {len(v)} dims')"),
    ("embedding azure", {"EMBED_PROFILE": "azure"},
     "from providers import embed; v = embed('HANA backup failed', 'query'); print(f'OK, {len(v)} dims')"),
    ("LLM claude", {"LLM_PROFILE": "claude"},
     "from providers import chat; print('OK:', chat('Answer in one short sentence.', 'Say hello in Slovak.'))"),
    ("LLM gemini", {"LLM_PROFILE": "gemini"},
     "from providers import chat; print('OK:', chat('Answer in one short sentence.', 'Say hello in Slovak.'))"),
]

for name, env, code in TESTS:
    result = subprocess.run([sys.executable, "-c", code], env={**os.environ, **env},
                            capture_output=True, text=True)
    out = (result.stdout or result.stderr).strip().splitlines()
    print(f"{name:<18} {out[-1] if out else 'no output'}")