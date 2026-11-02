#!/bin/bash
# 补跑：等当前 pass B 退出（它会在缺 m2_HP_s0 适配器时失败）→ 训 HP → 评 HP。
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

# 等 GPU 空出来（最多 40 分钟）
for i in $(seq 1 240); do
  pgrep -f 'scripts/diag_score.py' > /dev/null || break
  sleep 10
done
say "pass B 已退出，开始 HP 训练"
"$PY" scripts/train_drift.py --tag m2_HP_s0 --epochs 4 --bs 4 --accum 4 \
  --max-len 1024 --lora-r 16 --lr 2e-4 --seed 0 --style pab \
  --use-hardneg --hn-noinj --pref 1.0 --margin 0.5 >> "$L" 2>&1
say "HP 训练 rc=$?"
"$PY" scripts/diag_score.py --arms m2_HP_s0 --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "HP 评分 rc=$?"
say "CHAIN2_DONE"
