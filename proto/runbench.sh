#!/bin/sh
# Uso: runbench.sh <nombre> "<query>"  — corre bench.html en Chromium headless y espera results/<nombre>.json
cd "$(dirname "$0")"
N=$1; Q=$2
rm -f results/$N.json
fuser -k 8765/tcp >/dev/null 2>&1; sleep 0.5
python -I server.py 8765 & SP=$!
sleep 1
rm -rf ${TMPDIR:-/tmp}/bench-prof
chromium --headless=new --no-sandbox --user-data-dir=${TMPDIR:-/tmp}/bench-prof --autoplay-policy=no-user-gesture-required "http://localhost:8765/bench.html?name=$N&$Q" >/dev/null 2>&1 & CP=$!
for i in $(seq ${TIMEOUT:-600}); do [ -s results/$N.json ] && break; sleep 1; done
kill $CP $SP 2>/dev/null
[ -s results/$N.json ] && echo "OK results/$N.json" || echo "TIMEOUT"
