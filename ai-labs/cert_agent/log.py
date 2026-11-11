"""Timestamped progress output.

Everything goes to stderr, so stdout stays free for the JSON result of a run
(and for the MCP protocol when the server runs over stdio).
"""
from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from datetime import datetime


def step(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


@contextmanager
def timed(message: str):
    """Print the step before it starts and how long it took when it ends."""
    step(f"{message} ...")
    started = time.monotonic()
    try:
        yield
    except Exception as exc:
        step(f"{message}: FAILED after {time.monotonic() - started:.1f}s ({exc})")
        raise
    step(f"{message}: done in {time.monotonic() - started:.1f}s")
