#!/bin/bash
# 优先做 HB-sm（机制对照）与 S/H 多 seed；外部基线的 travel 部分留到最后
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain7.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }
HP="--epochs 4 --bs 4 --accum 4 --max-len 1024 --lora-r 16 --lr 2e-4 --style pab"

# 等 GPU 空闲（外部基线端到端全部退出）
for i in $(seq 1 240); do
  pgrep -f 'scripts/ad_run3.py' > /dev/null || break
  sleep 15
done
pkill -f 'vllm.entrypoints' 2>/dev/null || true
sleep 8
say "GPU 空闲，开始 HB-sm"

# 1) HB-sm
"$PY" scripts/train_drift.py --tag m2_SM_s0 $HP --seed 0 \
  --use-hardneg --hardneg data/hardneg_sm.jsonl >> "$L" 2>&1
say "SM 训练 rc=$?"
"$PY" scripts/diag_score.py --arms m2_SM_s0 --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "SM 评分 rc=$?"

# 2) S / H 的 seed 42 / 123
for S in 42 123; do
  say "训练 S seed=$S"
  "$PY" scripts/train_drift.py --tag "m2_S_s$S" $HP --seed "$S" >> "$L" 2>&1
  say "S seed=$S rc=$?"
  say "训练 H seed=$S"
  "$PY" scripts/train_drift.py --tag "m2_H_s$S" $HP --seed "$S" --use-hardneg >> "$L" 2>&1
  say "H seed=$S rc=$?"
done
"$PY" scripts/diag_score.py --arms m2_S_s42,m2_S_s123,m2_H_s42,m2_H_s123 \
  --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "seed 评分 rc=$?"
say "CHAIN7_DONE"
