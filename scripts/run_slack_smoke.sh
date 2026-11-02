#!/bin/bash
cd /data/projects/guardrails || exit 1
rm -f results/ad_v3/slack/smoke_scen.jsonl results/ad_v3/slack/smoke_trace.jsonl
rm -rf results/ad_v3/slack/smoke_logs
mkdir -p results/ad_v3/slack
setsid nohup /data/conda/envs/guard/bin/python scripts/ad_run2.py \
  --suite slack --mode both --limit 3 \
  --logdir results/ad_v3/slack/smoke_logs \
  --trace results/ad_v3/slack/smoke_trace.jsonl \
  --scen-out results/ad_v3/slack/smoke_scen.jsonl \
  --force > /tmp/slack_smoke.log 2>&1 < /dev/null &
echo launched
