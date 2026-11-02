#!/bin/bash
# M1/M2 四臂阶梯训练（1.5B / lr 2e-4 / 4 epochs / eff.batch 16 / max_len 1024）
#
#   S   只用 PAB-RD                      标准授权 SFT（内部基线，同协议重训）
#   H   + 攻击轨迹 hard negative（full）   M2：数据对齐
#   HV  + 同一调用的 noinj 反事实视图       反事实增强：切断「靠载荷文本判危险」的捷径
#   HP  + 同工具成对偏好（λ=1, margin .5）  M1：目标对齐（HP−HV 即目标本身的贡献）
#
# 用法: bash scripts/run_train_m2.sh [SEED]
set -u
SEED="${1:-0}"
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
HP="--epochs 4 --bs 4 --accum 4 --max-len 1024 --lora-r 16 --lr 2e-4 --seed $SEED --style pab"

echo "=== m2_S_s${SEED}  $(date +%H:%M:%S) ==="
"$PY" scripts/train_drift.py --tag "m2_S_s${SEED}" $HP 2>&1 | tail -18

echo "=== m2_H_s${SEED}  $(date +%H:%M:%S) ==="
"$PY" scripts/train_drift.py --tag "m2_H_s${SEED}" $HP --use-hardneg 2>&1 | tail -18

echo "=== m2_HV_s${SEED}  $(date +%H:%M:%S) ==="
"$PY" scripts/train_drift.py --tag "m2_HV_s${SEED}" $HP --use-hardneg --hn-noinj 2>&1 | tail -18

echo "=== m2_HP_s${SEED}  $(date +%H:%M:%S) ==="
"$PY" scripts/train_drift.py --tag "m2_HP_s${SEED}" $HP --use-hardneg --hn-noinj \
  --pref 1.0 --margin 0.5 2>&1 | tail -18

echo "M2_TRAIN_DONE $(date +%H:%M:%S)"
