#!/bin/bash
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/auto_b5.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }
say "停 vLLM"
pkill -f 'vllm.entrypoints' || true
sleep 10
say "训练 0.5B"
"$PY" scripts/train_drift.py --model /data/hf_cache/qwen0.5b --tag m2_HB05_s0 \
  --epochs 4 --bs 4 --accum 4 --max-len 1024 --lora-r 16 --lr 2e-4 --seed 0 --style pab \
  --use-hardneg --hardneg data/hardneg_bal.jsonl >> "$L" 2>&1
say "训练 rc=$?"
say "离线评分"
GUARD_DIAG_DIR=/data/projects/guardrails/results/p2/diag "$PY" scripts/diag_score.py \
  --arms m2_HB05_s0 --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "评分 rc=$?"
say "CPU 延迟"
env CUDA_VISIBLE_DEVICES= "$PY" scripts/b5_latency.py >> "$L" 2>&1
say "延迟 rc=$?"
say "B5_DONE"
