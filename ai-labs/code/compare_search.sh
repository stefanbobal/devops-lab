#!/bin/bash
# Run the same search experiments for several embedding models, each with its own threshold.
# Usage: ./compare_search.sh [load]   ("load" first reloads all tables)

declare -A THRESHOLD=( [nomic]=0.55 [bge]=0.55 [qwen]=0.60 [qwen8]=0.65 [gemini]=0.85 )
PROFILES="nomic bge qwen gemini"

if [ "$1" == "load" ]; then
  for p in $PROFILES; do
    echo "=== loading $p ==="
    EMBED_PROFILE=$p python load_incidents.py | tail -1
  done
fi

run() {   # $1 = title, rest = search.py arguments
  echo; echo "################ $1 ################"
  for p in $PROFILES; do
    echo "--- $p (threshold ${THRESHOLD[$p]})"
    EMBED_PROFILE=$p SIMILARITY_THRESHOLD=${THRESHOLD[$p]} python search.py "${@:2}" | tail -3
  done
}

run "1. Backup SSL, no filter"   "Backup failed, backint SSL handshake error"
run "2. Backup SSL, with filter" "Backup failed, backint SSL handshake error" backup HANA
run "3. Nonsense"                "Printer on floor 2 is out of paper"
run "4. Paraphrase"              "users complain everything takes forever" performance
