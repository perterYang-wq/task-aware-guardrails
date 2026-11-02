#!/bin/bash
# 外部基线端到端：PG2-86M 与 规则(γ==3 一律拦)，travel + slack 同一协议
set -u
cd /data/projects/guardrails
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain6.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

for combo in "slack pg2 injection_task_1,injection_task_3" \
             "slack rule:gamma injection_task_1,injection_task_3" \
             "travel pg2 injection_task_0,injection_task_1" \
             "travel rule:gamma injection_task_0,injection_task_1"; do
  set -- $combo
  S=$1; A=$2; I=$3
  say "=== $S / $A ==="
  bash scripts/e2e_guard.sh "$S" "$A" "$I" 0.72 '' '' block >> "$L" 2>&1
  say "$S/$A rc=$?"
done
say "CHAIN6_DONE"
