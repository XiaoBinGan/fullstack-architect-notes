#!/bin/bash
# Step 3: run the official Strata 0.2.2 (CUDA 13) container on GPU 1 (RTX 5090).
# Everything that persists lives under /workspace/Strata (bind mount), nothing elsewhere.
set -eu
source /workspace/Strata/scripts/env.sh

IMG=$STRATA_ROOT/images/strata-0.2.2-cuda13.tar
IMAGE=ghcr.nju.edu.cn/niko1221/strata:0.2.2-cuda13
NAME=strata
DATA=$STRATA_ROOT/strata-data
mkdir -p "$DATA"

API_KEY=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')

echo "### $(date -Is) starting container $NAME"
docker rm -f $NAME >/dev/null 2>&1 || true

docker run -d --name $NAME \
  --security-opt seccomp=unconfined \
  --gpus device=1 \
  --ulimit memlock=-1:-1 --shm-size 2g --stop-timeout 180 \
  -p 127.0.0.1:8899:8080 \
  -v "$DATA":/data \
  -e MODEL=Q2_0 \
  -e CONTEXT=32k \
  -e VISION=off \
  -e PARALLEL=1 \
  -e GPU=all \
  -e TUNE=skip \
  -e API_KEY="$API_KEY" \
  -e STRATA_SOURCE=modelscope \
  $IMAGE

echo "$API_KEY" > "$STRATA_ROOT/logs/api-key.txt"
chmod 600 "$STRATA_ROOT/logs/api-key.txt"
echo "API key: $API_KEY  (saved to logs/api-key.txt)"
sleep 15
docker ps --filter name=$NAME --format '{{.Names}} {{.Status}} {{.Ports}}'
echo "--- log ---"
docker logs --tail 30 $NAME 2>&1
