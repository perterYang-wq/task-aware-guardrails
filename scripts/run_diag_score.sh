#!/bin/bash
# 诊断打分：9 臂 × 4 视图 × 2370 调用（断点续跑，已完成的文件跳过）
# 3B 臂跳过多余视图，1.5B 臂先跑
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
PY=/data/conda/envs/guard/bin/python
LOG=/data/projects/guardrails/results/diag/score_all.log

setsid "$PY" scripts/diag_score.py --arms all --bs 32 --bs-3b 12 \
  > "$LOG" 2>&1 < /dev/null &
echo "pid=$! log=$LOG"
