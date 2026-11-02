#!/bin/bash
# 用法: run_travel_shard.sh <shard_name> <comma_separated_user_tasks>
set -e
SHARD="$1"
TASKS="$2"
cd /data/projects/guardrails
mkdir -p results/ad_v3/travel
setsid nohup /data/conda/envs/guard/bin/python scripts/ad_run2.py \
  --suite travel --mode attack --sys-version v3 \
  --only "$TASKS" \
  --logdir results/ad_v3/travel/logs_${SHARD} \
  --trace results/ad_v3/travel/trace_${SHARD}.jsonl \
  --scen-out results/ad_v3/travel/scen_${SHARD}.jsonl \
  --force > /tmp/travel_${SHARD}.log 2>&1 < /dev/null &
sleep 3
echo "shard ${SHARD} -> $(pgrep -fc 'ad_run2\.p[y]') 个采集进程在跑"
