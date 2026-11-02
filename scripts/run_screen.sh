#!/bin/bash
set -e
cd /data/projects/guardrails
mkdir -p results/ad_v3/ws_fix
rm -f results/ad_v3/ws_fix/screen_scen.jsonl results/ad_v3/ws_fix/screen_trace.jsonl
setsid nohup /data/conda/envs/guard/bin/python scripts/ad_run2.py \
  --suite workspace --mode attack --n-injections 1 \
  --logdir results/ad_v3/ws_fix/screen_logs \
  --trace results/ad_v3/ws_fix/screen_trace.jsonl \
  --scen-out results/ad_v3/ws_fix/screen_scen.jsonl \
  --force > /tmp/screen_ws.log 2>&1 < /dev/null &
sleep 3
pgrep -f 'ad_run2\.p[y]' >/dev/null && echo LAUNCHED || echo FAILED
