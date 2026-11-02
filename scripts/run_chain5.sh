#!/bin/bash
# 等 chain4 完成 -> 用 seed 42 的 HB 在 slack（in-distribution）跑端到端，验证 seed 稳定性
set -u
cd /data/projects/guardrails
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain5.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

for i in $(seq 1 400); do
  grep -q CHAIN4_DONE /data/projects/guardrails/results/chain4.log && break
  sleep 15
done
say "chain4 结束，启动 seed42 slack 端到端"
bash scripts/e2e_guard.sh slack m2_HB_s42 injection_task_1,injection_task_3 0.72 '' '' block >> "$L" 2>&1
say "seed42 slack rc=$?"
"$PY" scripts/e2e_analyze.py --run results/e2e/slack/m2_HB_s42_inj1-3 \
  --baseline results/ad_v3/slack/scen_merged.jsonl --policy block >> "$L" 2>&1
say "seed42 slack 分析 rc=$?"
say "CHAIN5_DONE"
