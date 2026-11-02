#!/bin/bash
# 7B 复现：安全显存配置（bs=1, accum=8, max_len 1024）
set -x
cd /data/projects/guardrails || exit 1
source ~/anaconda3/etc/profile.d/conda.sh
conda activate /data/conda/envs/guard
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
M=/home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28
D=data/pab_rd.jsonl
S=data/pab_rd_splits.json

echo "=== 7B LoRA (task) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab \
  --model $M --epochs 2 --bs 1 --accum 8 --max-len 1024 --lora-r 16 --tag o1_rd_7b
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M --bs 6 --adapter guard/adapters/o1_rd_7b --tag o1_rd_7b

echo "=== 7B LoRA (task-blind) ==="
python scripts/train_lora.py --data $D --splits $S --split pab --style pab \
  --model $M --epochs 2 --bs 1 --accum 8 --max-len 1024 --lora-r 16 --no-task \
  --tag o1_rd_7b_nt
python scripts/run_guard.py --data $D --splits $S --split '' --part test --style pab \
  --model $M --bs 6 --no-task --adapter guard/adapters/o1_rd_7b_nt --tag o1_rd_7b_nt

echo "=== SEVEN_B_DONE ==="
