#!/usr/bin/env bash
# Prepare connectivity to the existing database; delegate commands to Compose.
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
if [[ ! -f .env ]]; then
  printf '%s\n' 'First: cp .env.example .env; set the existing DB password and database. See DOCKER.md.' >&2
  exit 1
fi
if [[ "$(docker inspect --format '{{.State.Running}}' pgvector 2>/dev/null || true)" != true ]]; then
  printf '%s\n' 'Existing container pgvector must be running. Start it using the lab setup first.' >&2
  exit 1
fi
if ! docker network inspect llm-homelab >/dev/null 2>&1; then
  docker network create llm-homelab >/dev/null
fi
if ! docker network inspect --format '{{range .Containers}}{{println .Name}}{{end}}' llm-homelab | grep -Fxq pgvector; then
  docker network connect llm-homelab pgvector
fi
export LAB_UID="$(id -u)"
export LAB_GID="$(id -g)"
if (( $# == 0 )); then
  printf '%s\n' 'Usage: bash docker_lab.sh build | run --rm app python db_import.py --results /results [--execute] | up -d | ps | logs --tail 50 app'
  exit 0
fi
exec docker compose "$@"
