#!/bin/bash
# Re-bind the port to all interfaces (0.0.0.0) so the browser on the 100.100.x.x network can reach it.
# The model files stay in the volume: this is a warm start, no download.
set -eu
R=/workspace/Strata
API_KEY=$(cat "$R/logs/api-key.txt")
IMG=ghcr.nju.edu.cn/niko1221/strata:0.2.2-cuda13

docker rm -f strata >/dev/null 2>&1 || true

T0=$(date +%s)
docker run -d --name strata \
  --security-opt seccomp=unconfined \
  --gpus device=1 \
  --ulimit memlock=-1:-1 --shm-size 2g --stop-timeout 180 \
  -p 0.0.0.0:8899:8080 \
  -v "$R/strata-data":/data \
  -e MODEL=Q2_0 -e CONTEXT=32k -e VISION=off -e PARALLEL=1 \
  -e GPU=all -e TUNE=skip -e API_KEY="$API_KEY" \
  -e STRATA_SOURCE=modelscope \
  "$IMG" >/dev/null

echo "waiting for /health ..."
for i in $(seq 1 240); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "Authorization: Bearer $API_KEY" \
    http://127.0.0.1:8899/health 2>/dev/null || true)
  if [ "$code" = "200" ]; then
    echo "ready after $(( $(date +%s) - T0 ))s"
    break
  fi
  sleep 2
done

echo "=== docker port map ==="
docker port strata
echo "=== listening socket ==="
ss -tlnp 2>/dev/null | grep 8899
echo "=== health (loopback) ==="
curl -s -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8899/health
echo
echo "=== health (via the 100.100.152.243 address) ==="
curl -s -o /dev/null -w 'health via nic: %{http_code}\n' -H "Authorization: Bearer $API_KEY" \
  http://100.100.152.243:8899/health
echo "=== web page / (no key) ==="
curl -s -o /dev/null -w 'GET / without key: %{http_code}\n' http://100.100.152.243:8899/
echo "=== web page / (with key) ==="
curl -s -o /dev/null -w 'GET / with key: %{http_code}\n' -H "Authorization: Bearer $API_KEY" \
  http://100.100.152.243:8899/
