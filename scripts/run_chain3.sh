#!/bin/bash
# 补跑 2b：等所有 GPU 任务（训练/评分）退出 → 训练平衡版 HB → 评分 HB。
# 上一版只等了 diag_score，与 HP 训练撞车导致 OOM，这里改成同时等两类进程。
set -u
cd /data/projects/guardrails
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
PY=/data/conda/envs/guard/bin/python
L=/data/projects/guardrails/results/chain.log
AD=guard/adapters/m2_HB_s0
say() { echo "[$(date +%H:%M:%S)] $*" >> "$L"; }

busy() { pgrep -f 'scripts/train_drift.py|scripts/diag_score.py' > /dev/null; }
for i in $(seq 1 360); do
  busy || break
  sleep 10
done
if busy; then say "等待超时，GPU 仍被占用，放弃"; exit 1; fi
say "GPU 空闲，开始 HB（平衡版）训练"

if [ ! -f "$AD/adapter_config.json" ]; then
  "$PY" scripts/train_drift.py --tag m2_HB_s0 --epochs 4 --bs 4 --accum 4 \
    --max-len 1024 --lora-r 16 --lr 2e-4 --seed 0 --style pab \
    --use-hardneg --hardneg data/hardneg_bal.jsonl >> "$L" 2>&1
  say "HB 训练 rc=$?"
else
  say "HB 适配器已存在，跳过训练"
fi

"$PY" scripts/diag_score.py --arms m2_HB_s0 --views none,last3,full,noinj --bs 32 >> "$L" 2>&1
say "HB 评分 rc=$?"
say "CHAIN3_DONE"
