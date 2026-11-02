#!/bin/bash
# 给 M1/M2 各臂测 PAB-RD test（离线授权目标），供 m2_offline_eval.py 汇总。
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PY=/data/conda/envs/guard/bin/python
for T in m2_S_s0 m2_H_s0 m2_HV_s0 m2_HP_s0 m2_HB_s0; do
  [ -f "results/${T}_test.jsonl" ] && { echo "[skip] $T"; continue; }
  echo "[eval] $T"
  "$PY" scripts/run_guard.py --data data/pab_rd.jsonl --splits data/pab_rd_splits.json \
    --split "" --part test --style pab --model /data/hf_cache/qwen1.5b --bs 12 \
    --adapter "guard/adapters/$T" --tag "$T" > "/tmp/eval_$T.log" 2>&1
  echo "  rc=$?"
done
"$PY" scripts/m2_offline_eval.py --tags m2_S_s0 m2_H_s0 m2_HV_s0 m2_HP_s0 m2_HB_s0
