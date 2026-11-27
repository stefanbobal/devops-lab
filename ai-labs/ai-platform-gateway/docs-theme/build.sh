#!/usr/bin/env bash
# Build the themed swagger-ui.css for the gateway's /docs page.
# Takes the stock CSS from the pinned LiteLLM image (same tag as docker-compose.yml)
# and appends saitron-dark.css. The output is gitignored; rerun after an image upgrade.
#
#   ./docs-theme/build.sh && docker compose up -d
set -euo pipefail
cd "$(dirname "$0")"
log() { echo "[$(date +%H:%M:%S)] $*" >&2; }

image=$(sed -nE 's/^\s*image:\s*(ghcr\.io\/berriai\/litellm:[^ #]+).*/\1/p' ../docker-compose.yml)
css=/app/.venv/lib/python3.13/site-packages/litellm/proxy/swagger/swagger-ui.css
[ -n "$image" ] || { log "no LiteLLM image found in docker-compose.yml"; exit 1; }

log "step 1/2: copy stock swagger-ui.css out of $image"
docker run --rm --entrypoint cat "$image" "$css" > swagger-ui.base.css.tmp
[ -s swagger-ui.base.css.tmp ] || { log "empty file, path changed in this image? ($css)"; exit 1; }

log "step 2/2: append saitron-dark.css -> swagger-ui.css"
{ cat swagger-ui.base.css.tmp; printf '\n/* ---- theme appended by build.sh from %s ---- */\n' "$image"; cat saitron-dark.css; } > swagger-ui.css
rm swagger-ui.base.css.tmp
log "done: $(wc -c < swagger-ui.css) bytes in docs-theme/swagger-ui.css"
