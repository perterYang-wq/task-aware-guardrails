#!/bin/bash
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/auto_b6_retrain.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

say "停止 vLLM 以腾出显存"
pkill -f 'vllm.entrypoints' || true
sleep 10

say "训练 m2_HBmeta_s0"
"$PY" scripts/train_drift.py --tag m2_HBmeta_s0 --epochs 4 --bs 4 --accum 4 \
  --max-len 1024 --lora-r 16 --lr 2e-4 --seed 0 --style pab \
  --use-hardneg --hardneg data/hardneg_bal_meta.jsonl >> "$L" 2>&1
say "训练 rc=$?"

say "离线评分"
GUARD_DIAG_DIR=/data/projects/guardrails/results/p2/diag "$PY" scripts/diag_score.py \
  --arms m2_HBmeta_s0 --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "评分 rc=$?"

say "端到端：meta 变形 + 新守卫"
bash scripts/e2e_guard.sh travel m2_HBmeta_s0 injection_task_1 0.72 '' _b6meta2 block attack 0 meta
say "e2e rc=$?"
say "B6_RETRAIN_DONE"
