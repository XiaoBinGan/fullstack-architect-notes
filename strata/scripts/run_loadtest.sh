#!/bin/bash
# Full load test: starts the host resource sampler, the server metrics sampler, then every stage.
set -u
R=/workspace/Strata
PY=$R/data/terminal/current/python/bin/python3
OUT=$R/results/loadtest
mkdir -p "$OUT" "$R/logs"

MINUTES=${MINUTES:-10}

echo "### $(date -Is) starting host sampler"
$PY "$R/client/sampler.py" "$OUT/host-resources.csv" 5400 2 > "$R/logs/sampler-load.log" 2>&1 &
SPID=$!

echo "### $(date -Is) starting server metrics sampler"
$PY "$R/client/metrics_sampler.py" "$OUT/server-metrics.jsonl" 5400 5 > "$R/logs/metrics-sampler.log" 2>&1 &
MPID=$!

sleep 3
echo "### $(date -Is) load test begins (sustained ${MINUTES} min)"
$PY "$R/client/loadtest.py" "$OUT" \
  --server http://127.0.0.1:8899 \
  --keyfile "$R/logs/api-key.txt" \
  --stages sweep,sustained,longctx,vision,overload \
  --sweep-clients 1,2,4,8,16 \
  --sustained-clients 4 \
  --minutes "$MINUTES" \
  --out-tokens 192 \
  --rounds 2 2>&1 | tee "$R/logs/loadtest.log"

echo "### $(date -Is) stopping samplers"
touch "$OUT/server-metrics.jsonl.stop"
kill $SPID $MPID 2>/dev/null || true
wait 2>/dev/null || true
echo "### sampler files:"
wc -l "$OUT/host-resources.csv" "$OUT/server-metrics.jsonl" 2>/dev/null
echo "### finished $(date -Is)"
