#!/bin/bash
# 用法: run_slack_shard.sh <SHARD> <逗号分隔的 user_task 列表>
set -u
SHARD="${1:?need shard}"
ONLY="${2:?need task list}"
cd /data/projects/guardrails || exit 1
mkdir -p results/ad_v3/slack
rm -f  "results/ad_v3/slack/scen_${SHARD}.jsonl" "results/ad_v3/slack/trace_${SHARD}.jsonl"
rm -rf "results/ad_v3/slack/logs_${SHARD}"
setsid nohup /data/conda/envs/guard/bin/python scripts/ad_run2.py \
  --suite slack --mode both \
  --only "$ONLY" \
  --logdir "results/ad_v3/slack/logs_${SHARD}" \
  --trace  "results/ad_v3/slack/trace_${SHARD}.jsonl" \
  --scen-out "results/ad_v3/slack/scen_${SHARD}.jsonl" \
  --force > "/tmp/slack_${SHARD}.log" 2>&1 < /dev/null &
echo "shard ${SHARD} launched: ${ONLY}"
