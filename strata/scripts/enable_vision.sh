#!/bin/bash
# Enable image input with the CPU picture reader (the GPU has only ~410 MiB free,
# the GPU reader needs ~1-1.4 GB, the CPU reader takes none).
# Keeps the 0.0.0.0:8899 binding. Model files stay in the volume (no model re-download);
# only the ~0.9 GB picture-reader file is added once.
set -eu
R=/workspace/Strata
API_KEY=$(cat "$R/logs/api-key.txt")
IMG=ghcr.nju.edu.cn/niko1221/strata:0.2.2-cuda13

cd "$R"

docker rm -f strata >/dev/null 2>&1 || true

T0=$(date +%s)
nohup docker run --name strata \
  --security-opt seccomp=unconfined \
  --gpus device=1 \
  --ulimit memlock=-1:-1 --shm-size 2g --stop-timeout 180 \
  -p 0.0.0.0:8899:8080 \
  -v "$R/strata-data":/data \
  -e MODEL=Q2_0 -e CONTEXT=32k -e VISION=cpu -e PARALLEL=1 \
  -e GPU=all -e TUNE=skip -e API_KEY="$API_KEY" \
  -e STRATA_SOURCE=modelscope \
  "$IMG" > "$R/logs/vision-run.log" 2>&1 &
echo "started; waiting for readiness (downloads ~0.9 GB picture reader the first time)"

for i in $(seq 1 900); do
  code=$(curl -s -o /tmp/h.json -w '%{http_code}' -m 5 -H "Authorization: Bearer $API_KEY" \
    http://127.0.0.1:8899/health 2>/dev/null || true)
  if [ "$code" = "200" ]; then
    echo "ready after $(( $(date +%s) - T0 ))s"
    cat /tmp/h.json
    echo
    break
  fi
  if [ $((i % 20)) -eq 0 ]; then
    echo "[$((i*2))s] $(docker logs --tail 1 strata 2>&1 | tail -1 | cut -c1-120)"
  fi
  sleep 2
done

echo
echo "=== docker port ==="
docker port strata
echo "=== log tail ==="
docker logs --tail 12 strata 2>&1 | tail -12
