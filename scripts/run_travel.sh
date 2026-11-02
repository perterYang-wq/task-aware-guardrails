#!/bin/bash
set -e
cd /data/projects/guardrails
mkdir -p results/ad_v3/travel
rm -f results/ad_v3/travel/trace.jsonl results/ad_v3/travel/scen.jsonl
rm -rf results/ad_v3/travel/logs
setsid nohup /data/conda/envs/guard/bin/python scripts/ad_run2.py \
  --suite travel --mode both --sys-version v3 \
  --logdir results/ad_v3/travel/logs \
  --trace results/ad_v3/travel/trace.jsonl \
  --scen-out results/ad_v3/travel/scen.jsonl \
  --force > /tmp/travel_run.log 2>&1 < /dev/null &
sleep 3
pgrep -f 'ad_run2\.p[y]' >/dev/null && echo LAUNCHED || echo FAILED
