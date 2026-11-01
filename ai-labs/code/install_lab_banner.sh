#!/usr/bin/env bash
# Run on the Ubuntu VM as sapops. Installs an interactive Bash login reminder.
set -euo pipefail
if [[ "$(id -un)" != sapops || "$(hostname -s)" != k8s-lab ]]; then
  printf '%s\n' 'Run this installer as sapops on k8s-lab (without sudo).' >&2
  exit 1
fi
LAB_BANNER_DIR="$HOME/.config/ai-lab"
mkdir -p "$LAB_BANNER_DIR"
cat > "$LAB_BANNER_DIR/login-banner.sh" <<'BANNER'
# AI lab reminder: interactive Bash only, on the intended user and host.
case $- in *i*) ;; *) return ;; esac
if [[ "$(id -un)" != sapops || "$(hostname -s)" != k8s-lab ]]; then
  return
fi
cat <<'TEXT'

======================================================================
  SAPOPS AI LAB | sapops@k8s-lab
======================================================================
  DENNY START: prostredie -> Docker/pgvector -> Ollama -> skripty

  1. Otvor lab a aktivuj prostredie:
     cd ~/devops-lab/ai-labs/code
     source .venv/bin/activate
     which python

  2. Automaticka kontrola labu:
     bash lab.sh
     Ocakavany vysledok: Lab ready.

  3. Ak budes pouzivat cloud (platene API probes):
     bash lab.sh --cloud

  4. Spusti RAG plan cez kontrolu labu (bez API volani):
     bash lab.sh rag_test.py --order by-model

  Rucna diagnostika pri chybe:
     docker ps
     curl --fail --max-time 10 http://192.168.178.25:11434/api/tags

  Ollama vo VM .env: OLLAMA_HOST=http://192.168.178.25:11434
  Pred plnym testom pouzi runbook: preflight, smoke, prepare-contexts.
  Runbook: ~/devops-lab/ai-labs/RUNBOOK-RAG-2026-10-31.md

  Zobrazenie navodu znova: source ~/.config/ai-lab/login-banner.sh
======================================================================

TEXT
BANNER
LAB_BANNER_SOURCE='[[ -r "$HOME/.config/ai-lab/login-banner.sh" ]] && source "$HOME/.config/ai-lab/login-banner.sh"'
touch "$HOME/.bashrc"
if ! grep -Fqx -- "$LAB_BANNER_SOURCE" "$HOME/.bashrc"; then
  cp -p "$HOME/.bashrc" "$LAB_BANNER_DIR/bashrc.before-banner.$(date +%Y%m%d%H%M%S).$$"
  printf '\n# SAPOPS AI lab login reminder\n%s\n' "$LAB_BANNER_SOURCE" >> "$HOME/.bashrc"
fi
printf '%s\n' 'Banner installed for interactive Bash sessions.'
printf '%s\n' 'Preview: source ~/.config/ai-lab/login-banner.sh'
printf '%s\n' 'Disable: remove its source line from ~/.bashrc, or rename ~/.config/ai-lab/login-banner.sh'
