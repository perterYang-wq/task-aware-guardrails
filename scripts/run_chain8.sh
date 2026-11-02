#!/bin/bash
# 外部基线的剩余端到端：slack 规则 → travel 规则 → travel PG2
set -u
cd /data/projects/guardrails
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain8.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

for i in $(seq 1 400); do
  grep -q CHAIN7_DONE /data/projects/guardrails/results/chain7.log && break
  sleep 20
done
say "chain7 结束，开始外部基线剩余端到端"

for combo in "slack rule:gamma injection_task_1,injection_task_3" \
             "travel rule:gamma injection_task_0,injection_task_1" \
             "travel pg2 injection_task_0,injection_task_1"; do
  set -- $combo
  S=$1; A=$2; I=$3
  say "=== $S / $A ==="
  bash scripts/e2e_guard.sh "$S" "$A" "$I" 0.72 '' '' block >> "$L" 2>&1
  say "$S/$A rc=$?"
  SAFE=$(echo "$A" | tr ': ' '--')
  SUF="_inj$(echo "$I" | sed 's/injection_task_//g; s/,/-/g')"
  "$PY" scripts/e2e_analyze.py --run "results/e2e/$S/$SAFE$SUF" \
    --baseline "results/ad_v3/$S/scen_merged.jsonl" --policy block >> "$L" 2>&1
  say "$S/$A 分析 rc=$?"
done
say "CHAIN8_DONE"
