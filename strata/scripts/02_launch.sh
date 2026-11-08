#!/bin/bash
# Step 2: download engine + model and start the Strata server (GPU 1 = RTX 5090).
set -u
source /workspace/Strata/scripts/env.sh

export STRATA_SOURCE=modelscope
export HF_ENDPOINT=https://hf-mirror.com

LOG=$STRATA_ROOT/logs/launch.log
PIDFILE=$STRATA_ROOT/logs/launch.pid

echo "### $(date -Is) launching strata" > "$LOG"
echo "source=modelscope hf_endpoint=$HF_ENDPOINT" >> "$LOG"

nohup strata launch \
  --model q2_0 \
  --gpu 1 \
  --context 64k \
  --vision cpu \
  --parallel 1 \
  --data-dir "$STRATA_ROOT/models" \
  --access local \
  --port 8899 \
  --tune skip \
  --no-tui \
  --yes \
  >> "$LOG" 2>&1 &

echo $! > "$PIDFILE"
echo "started pid $(cat $PIDFILE), log $LOG"
sleep 20
tail -25 "$LOG"
