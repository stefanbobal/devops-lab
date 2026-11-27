#!/usr/bin/env bash
# Use: bash lab.sh [--cloud] [--] [script.py arguments...]
set -euo pipefail
LAB_CODE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_CODE_DIR"
if [[ ! -f .venv/bin/activate ]]; then
  printf '%s\n' 'Missing .venv/bin/activate in lab code directory.' >&2
  exit 1
fi
source .venv/bin/activate
LAB_CHECK_ARGS=()
if [[ "${1:-}" == --cloud ]]; then
  LAB_CHECK_ARGS+=(--cloud)
  shift
fi
if [[ "${1:-}" == -- ]]; then
  shift
fi
python lab_start.py "${LAB_CHECK_ARGS[@]}"
if (( $# )); then
  exec python "$@"
fi
