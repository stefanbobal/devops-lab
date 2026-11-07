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
  CODE_BANKA (covenant agent, vlastna DB pgvector-banka, port 5433)
======================================================================
  1. Otvor lab a aktivuj jeho vlastne prostredie:
     cd ~/devops-lab/ai-labs/code_banka
     source .venv/bin/activate

  2. DB a kontrola labu:
     docker compose up -d        (alebo: docker start pgvector-banka)
     bash lab.sh                 Ocakavany vysledok: Lab ready.

  3. Dokumenty do DB (po zmene chunkovania alebo dat vzdy znova):
     python generate_data.py
     for p in bge azure gemini; do EMBED_PROFILE=$p python load_documents.py; done

  4. Test retrievalu T2 na dev sade (testovacia sada iba s --final):
     python t2_retrieval.py --tag nazov_behu

  Navod a vysledky: code_banka/README.md, T2_retrieval_embeddings.md
======================================================================

TEXT

# Docker stav: co bezi a co treba spustit.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  _lab_missing=()
  printf '  DOCKER STAV:\n'
  for _c in pgvector pgvector-banka app_llm_homelab-app-1 app_llm_homelab-judge-1; do
    _st="$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$_c" 2>/dev/null)"
    if [[ "$_st" == running* && "$_st" != *unhealthy* && "$_st" != *starting* ]]; then
      printf '    [ OK ] %-26s %s\n' "$_c" "$_st"
    else
      printf '    [ !! ] %-26s %s\n' "$_c" "${_st:-neexistuje}"
      _lab_missing+=("$_c")
    fi
  done
  if (( ${#_lab_missing[@]} )); then
    printf '\n  TREBA SPUSTIT:\n'
    [[ " ${_lab_missing[*]} " == *" pgvector "* ]] && printf '    docker start pgvector\n'
    [[ " ${_lab_missing[*]} " == *" pgvector-banka "* ]] && printf '    docker start pgvector-banka   (alebo: cd ~/devops-lab/ai-labs/code_banka && docker compose up -d)\n'
    [[ " ${_lab_missing[*]} " == *app_llm_homelab-* ]] && printf '    cd ~/devops-lab/ai-labs/app_llm_homelab && bash docker_lab.sh up -d\n'
    printf '    Po zmene kodu: bash docker_lab.sh build app judge && bash docker_lab.sh up -d\n'
  fi
  printf '\n'
  unset _lab_missing _c _st
else
  printf '  DOCKER STAV: docker nie je dostupny (spusti docker / skontroluj prava)\n\n'
fi
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
